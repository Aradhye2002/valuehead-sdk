"""Streaming-append client for the ValueHead trace evaluation API.

Use this when you produce trace messages incrementally (e.g. an RL rollout
that runs for minutes) and you want the judge to score each turn as it
arrives, rather than waiting for the whole conversation to finish.

Example
-------
    async with StreamingSession.open(api_key, initial_messages=[...]) as s:
        async for event in s.stream():       # SSE judgement events
            print(event)
        # ... your rollout loop ...
        await s.append([assistant_msg, tool_msg])
        ...
        # session is auto-closed on context exit
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

from valuehead.models import SessionDetail, SubmitResult


class StreamingError(Exception):
    """Raised on streaming-API errors (auth, validation, network)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class JudgementEvent:
    """One SSE event from the judge as it streams turn judgements."""

    __slots__ = ("session_id", "turn", "judgements")

    def __init__(self, session_id: str, turn: int, judgements: dict[str, Any]):
        self.session_id = session_id
        self.turn = turn
        self.judgements = judgements

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JudgementEvent":
        return cls(
            session_id=payload.get("session_id", ""),
            turn=int(payload.get("turn", 0)),
            judgements=payload.get("judgements", {}),
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"JudgementEvent(turn={self.turn}, n_judgements={len(self.judgements)})"


class StreamingSession:
    """Async client for one streaming trace session.

    Construct via ``await StreamingSession.open(...)`` or use the
    ``streaming_session`` async context manager helper. The session is
    auto-closed (status='closing') when the context exits, so the judge
    can finalize and emit a trajectory judgement.
    """

    def __init__(
        self,
        *,
        session_id: str,
        client: httpx.AsyncClient,
        owns_client: bool,
    ):
        self.session_id = session_id
        self._client = client
        self._owns_client = owns_client
        self._closed = False

    # ── factory ─────────────────────────────────────────────────────────────

    @classmethod
    async def open(
        cls,
        api_key: str,
        *,
        base_url: str = "https://valuehead-production.up.railway.app",
        initial_messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        instructions: str = "",
        evaluate_safety: bool = False,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> "StreamingSession":
        """Open a new streaming session and return an immediately-usable handle."""
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                base_url=f"{base_url.rstrip('/')}/api/v1",
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )
        payload: dict[str, Any] = {
            "initial_messages": initial_messages or [],
            "metadata": metadata or {},
            "instructions": instructions,
            "evaluate_safety": evaluate_safety,
        }
        try:
            resp = await client.post("/traces/streaming", json=payload)
        except Exception:
            if owns_client:
                await client.aclose()
            raise

        if resp.status_code != 201:
            if owns_client:
                await client.aclose()
            raise StreamingError(
                f"Failed to open streaming session ({resp.status_code}): {resp.text}",
                resp.status_code,
            )
        data = resp.json()
        return cls(
            session_id=data["session_id"],
            client=client,
            owns_client=owns_client,
        )

    # ── operations ──────────────────────────────────────────────────────────

    async def append(self, messages: list[dict[str, Any]]) -> SubmitResult:
        """Append more messages to this session and wake the judge."""
        if self._closed:
            raise StreamingError("Cannot append to a closed session")
        resp = await self._client.post(
            f"/traces/{self.session_id}/messages",
            json={"messages": messages},
        )
        if resp.status_code != 200:
            raise StreamingError(
                f"Append failed ({resp.status_code}): {resp.text}", resp.status_code
            )
        return SubmitResult(**resp.json())

    async def close(self) -> SubmitResult:
        """Mark the session as closed; the judge will finalize remaining turns."""
        if self._closed:
            return SubmitResult(session_id=self.session_id, status="closing")
        self._closed = True
        resp = await self._client.post(f"/traces/{self.session_id}/close")
        if resp.status_code != 200:
            raise StreamingError(
                f"Close failed ({resp.status_code}): {resp.text}", resp.status_code
            )
        return SubmitResult(**resp.json())

    async def get(self) -> SessionDetail:
        """Fetch the current session state (status, judgements, trajectory)."""
        resp = await self._client.get(f"/traces/{self.session_id}")
        if resp.status_code != 200:
            raise StreamingError(
                f"Get failed ({resp.status_code}): {resp.text}", resp.status_code
            )
        return SessionDetail(**resp.json())

    async def stream(self) -> AsyncIterator[JudgementEvent]:
        """Yield judgement events as the judge processes each turn.

        Iteration ends when the server emits its terminal `done` SSE event,
        which happens after `close()` has been called and the trajectory
        evaluation has finished (or the session has failed).
        """
        # We use a fresh httpx.AsyncClient for the streaming GET so it can
        # outlive request-scoped timeouts on the shared client.
        base_url = str(self._client.base_url)
        headers = dict(self._client.headers)
        async with httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=httpx.Timeout(None, connect=30)
        ) as sse_client:
            async with sse_client.stream(
                "GET", f"/traces/{self.session_id}/stream"
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise StreamingError(
                        f"Stream failed ({resp.status_code}): {body.decode(errors='replace')}",
                        resp.status_code,
                    )
                event_name: str | None = None
                async for line in resp.aiter_lines():
                    if not line:
                        # SSE event delimiter — already handled per-line below.
                        continue
                    if line.startswith(":"):
                        # SSE comment / keep-alive ping
                        continue
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                        continue
                    if line.startswith("data:"):
                        raw = line.removeprefix("data:").strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if event_name == "judgement":
                            yield JudgementEvent.from_payload(payload)
                        elif event_name in ("done", "error"):
                            return
                        event_name = None

    async def aclose(self) -> None:
        """Close session if open and release the underlying HTTP client."""
        try:
            if not self._closed:
                try:
                    await self.close()
                except Exception:
                    # Best-effort — don't mask the original error
                    pass
        finally:
            if self._owns_client:
                await self._client.aclose()

    async def __aenter__(self) -> "StreamingSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


@asynccontextmanager
async def streaming_session(
    api_key: str,
    *,
    base_url: str = "https://valuehead-production.up.railway.app",
    initial_messages: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    instructions: str = "",
    evaluate_safety: bool = False,
    timeout: float = 60.0,
):
    """Async context manager wrapping ``StreamingSession.open`` + ``aclose``."""
    session = await StreamingSession.open(
        api_key,
        base_url=base_url,
        initial_messages=initial_messages,
        metadata=metadata,
        instructions=instructions,
        evaluate_safety=evaluate_safety,
        timeout=timeout,
    )
    try:
        yield session
    finally:
        await session.aclose()


async def wait_for_completion(
    session: StreamingSession,
    *,
    poll_interval: float = 1.0,
    timeout: float = 600.0,
) -> SessionDetail:
    """Poll until the session reaches a terminal status (completed / failed)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        detail = await session.get()
        if detail.status in ("completed", "failed"):
            return detail
        await asyncio.sleep(poll_interval)
    raise StreamingError(
        f"Session {session.session_id} did not complete within {timeout}s"
    )
