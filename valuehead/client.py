"""ValueHead Python SDK client."""

from __future__ import annotations

import time
from typing import Any

import httpx

from valuehead.models import (
    SessionDetail,
    SessionsListResponse,
    SubmitResult,
)


class ValueHeadError(Exception):
    """Base exception for ValueHead SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(ValueHeadError):
    """Raised on 401/403 responses."""
    pass


class NotFoundError(ValueHeadError):
    """Raised on 404 responses."""
    pass


class EvaluationTimeoutError(ValueHeadError):
    """Raised when wait() exceeds its timeout."""
    pass


class ValueHead:
    """Synchronous client for the ValueHead trace evaluation API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://valuehead-production.up.railway.app",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self._base_url}/api/v1",
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    def submit(
        self,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        instructions: str = "",
    ) -> SubmitResult:
        """Submit a trace for async evaluation. Returns immediately.

        Parameters
        ----------
        messages : OpenAI-format conversation messages
        metadata : optional extra metadata tags
        instructions : optional custom evaluation instructions for the
            trajectory-level judgement (e.g. "penalise any incorrect
            tool calls", "only evaluate the final result")
        """
        payload: dict[str, Any] = {"messages": messages}
        if metadata:
            payload["metadata"] = metadata
        if instructions:
            payload["instructions"] = instructions
        resp = self._request("POST", "/traces", json=payload)
        return SubmitResult(**resp)

    def submit_text(
        self,
        text: str,
        context: str = "",
        metadata: dict[str, Any] | None = None,
        first_speaker_role: str = "user",
        instructions: str = "",
    ) -> SubmitResult:
        """Submit a raw conversation transcript for parsing and evaluation.

        Parameters
        ----------
        text : raw conversation transcript as a single string
        context : optional hint (e.g. "customer support call")
        metadata : optional extra metadata tags
        first_speaker_role : "user" or "assistant" — who speaks first
        instructions : optional custom trajectory evaluation instructions
        """
        payload: dict[str, Any] = {"text": text}
        if context:
            payload["context"] = context
        if metadata:
            payload["metadata"] = metadata
        if first_speaker_role != "user":
            payload["first_speaker_role"] = first_speaker_role
        if instructions:
            payload["instructions"] = instructions
        resp = self._request("POST", "/traces/text", json=payload)
        return SubmitResult(**resp)

    def submit_voice(
        self,
        file_path: str,
        metadata: dict[str, Any] | None = None,
        human_speaker: str | None = None,
        speakers_expected: int | None = None,
        first_speaker_role: str = "user",
        instructions: str = "",
    ) -> SubmitResult:
        """Submit a voice recording for transcription and evaluation.

        Parameters
        ----------
        file_path : path to an audio file (wav, mp3, ogg, m4a, etc.)
        metadata : optional extra metadata tags
        human_speaker : optional speaker ID to map as the human
        speakers_expected : hint for diarization (e.g. 2 for a two-person call)
        first_speaker_role : "user" or "assistant" — who speaks first
        instructions : optional custom trajectory evaluation instructions
        """
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f, "application/octet-stream")}
            data: dict[str, str] = {}
            if metadata:
                import json as _json
                data["metadata"] = _json.dumps(metadata)
            if human_speaker:
                data["human_speaker"] = human_speaker
            if speakers_expected is not None:
                data["speakers_expected"] = str(speakers_expected)
            if first_speaker_role != "user":
                data["first_speaker_role"] = first_speaker_role
            if instructions:
                data["instructions"] = instructions
            resp = self._client.post("/traces/voice", files=files, data=data)

        if resp.status_code == 201:
            return SubmitResult(**resp.json())
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {resp.text}", resp.status_code
            )
        if resp.status_code >= 400:
            raise ValueHeadError(
                f"API error {resp.status_code}: {resp.text}", resp.status_code
            )
        return SubmitResult(**resp.json())

    def get(self, session_id: str) -> SessionDetail:
        """Get full session state including judgements."""
        resp = self._request("GET", f"/traces/{session_id}")
        return SessionDetail(**resp)

    def list(self, limit: int = 50, offset: int = 0) -> SessionsListResponse:
        """List evaluation sessions (most recent first)."""
        resp = self._request("GET", "/traces", params={"limit": limit, "offset": offset})
        return SessionsListResponse(**resp)

    def delete(self, session_id: str) -> None:
        """Delete a session and its results."""
        self._request("DELETE", f"/traces/{session_id}")

    def wait(
        self,
        session_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
    ) -> SessionDetail:
        """Poll until evaluation completes or fails. Raises on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            session = self.get(session_id)
            if session.status in ("completed", "failed"):
                return session
            time.sleep(poll_interval)
        raise EvaluationTimeoutError(
            f"Session {session_id} did not complete within {timeout}s"
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> ValueHead:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = self._client.request(method, path, json=json, params=params)

        if resp.status_code == 204:
            return {}
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {resp.text}", resp.status_code
            )
        if resp.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {path}", resp.status_code
            )
        if resp.status_code >= 400:
            raise ValueHeadError(
                f"API error {resp.status_code}: {resp.text}", resp.status_code
            )

        return resp.json()
