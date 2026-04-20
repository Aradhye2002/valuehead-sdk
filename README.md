# ValueHead

LLM-as-judge observability for AI agents. Submit your agent's conversation traces and get back per-turn scores, tool call evaluations, and trajectory-level assessments — all powered by rubric-based LLM judging.

**Website & Dashboard**: [valuehead.ai](https://valuehead.ai)

## What is ValueHead?

ValueHead is an observability platform that evaluates multi-turn AI agent conversations. It scores each turn as **helpful (+1)**, **neutral (0)**, or **harmful (-1)** with detailed reasoning, and provides an overall trajectory assessment of the conversation.

It works with:

- **Tool-calling agents** — evaluates tool selection, parameter accuracy, and response synthesis
- **Conversational agents** — evaluates response quality, hallucination, and consistency
- **Voice AI agents** — transcribes audio recordings and evaluates the conversation
- **Raw text transcripts** — auto-parses speaker roles and evaluates

## Installation

```bash
pip install valuehead
```

Or install from source:

```bash
pip install git+https://github.com/Aradhye2002/valuehead-sdk.git
```

## Quick start

1. Sign up at [valuehead.ai](https://valuehead.ai) and get your API key from Settings
2. Submit a trace:

```python
from valuehead import ValueHead

client = ValueHead(api_key="vh_your_api_key_here")

result = client.submit(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather in London?"},
        {"role": "assistant", "content": "Let me check that for you.", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {
                "name": "get_weather", "arguments": "{\"city\": \"London\"}"
            }}
        ]},
        {"role": "tool", "content": "{\"temp\": 15, \"condition\": \"cloudy\"}", "tool_call_id": "call_1"},
        {"role": "assistant", "content": "London is currently 15°C and cloudy."},
    ],
    metadata={"agent": "weather-bot", "version": "1.0"},
)

# Wait for evaluation to complete
session = client.wait(result.session_id)

# Print results
print(f"Turns: {session.total_turns}, Net score: {session.summary.net_score}")
for turn_num, j in session.judgements.items():
    score = f"+{j.score}" if j.score > 0 else str(j.score)
    tools = f" [{len(j.tool_calls)} tools]" if j.tool_calls else ""
    print(f"  Turn {j.turn}: {score}{tools} — {j.turn_reasoning[:100]}")
```

## Input formats

### 1. Structured conversation traces

Submit OpenAI-format messages with `system`, `user`, `assistant`, and `tool` roles. Each user message starts a new evaluation turn.

```python
result = client.submit(
    messages=[
        {"role": "system", "content": "You are a booking assistant."},
        {"role": "user", "content": "Book me a flight to Paris."},
        {"role": "assistant", "content": "Searching for flights.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {
                "name": "search_flights", "arguments": "{\"destination\": \"Paris\"}"
            }}
        ]},
        {"role": "tool", "content": "{\"flights\": [{\"id\": \"FL123\", \"price\": 450}]}", "tool_call_id": "c1"},
        {"role": "assistant", "content": "I found a flight to Paris for $450. Shall I book it?"},
        {"role": "user", "content": "Yes, book it."},
        {"role": "assistant", "content": "Booking now.", "tool_calls": [
            {"id": "c2", "type": "function", "function": {
                "name": "book_flight", "arguments": "{\"flight_id\": \"FL123\"}"
            }}
        ]},
        {"role": "tool", "content": "{\"confirmation\": \"BK789\"}", "tool_call_id": "c2"},
        {"role": "assistant", "content": "Your flight is booked! Confirmation: BK789."},
    ],
    metadata={"agent": "travel-bot"},
)
```

Supports both OpenAI-style `tool_calls` arrays and XML-style `<tool_call>` tags in message content.

### 2. Voice recordings

Upload audio files (wav, mp3, ogg, m4a, etc.) for automatic transcription with speaker diarization, then evaluation.

```python
result = client.submit_voice(
    "recording.ogg",
    speakers_expected=2,
    first_speaker_role="user",
    metadata={"call_type": "support"},
)
session = client.wait(result.session_id)
```

Parameters:
- `file_path` — path to an audio file
- `speakers_expected` — hint for diarization (e.g. `2` for a two-person call)
- `human_speaker` — override which speaker ID maps to the human role
- `first_speaker_role` — `"user"` (default) or `"assistant"` for outbound/agent-initiated calls
- `metadata` — extra tags

Supports multilingual audio with automatic language detection. When diarization detects 2+ speakers, they are mapped to user/assistant automatically. Single-speaker recordings fall back to LLM-based speaker identification.

### 3. Raw text transcripts

Submit unstructured conversation text. ValueHead's LLM parser identifies speakers and splits into turns before evaluation.

```python
result = client.submit_text(
    text="""
    Agent: Thank you for calling Acme Support, how can I help?
    Customer: Hi, my internet has been down since yesterday.
    Agent: I'm sorry to hear that. Let me check your account.
    Customer: My account number is 12345.
    Agent: I can see there's an outage in your area. It should be resolved by 5 PM today.
    Customer: Okay, thanks for letting me know.
    """,
    context="ISP customer support call",
    metadata={"department": "technical"},
)
session = client.wait(result.session_id)
```

Parameters:
- `text` — the raw conversation as a string
- `context` — optional hint to help the parser (e.g. "recruitment call", "tech support chat")
- `first_speaker_role` — `"user"` (default) or `"assistant"`
- `metadata` — extra tags

### 4. Batch submission

Submit multiple traces at once via the API:

```bash
curl -X POST https://valuehead-production.up.railway.app/api/v1/traces/batch \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: vh_your_key" \
  -d '{"traces": [{"messages": [...], "metadata": {...}}, ...]}'
```

## API reference

### `ValueHead(api_key, base_url, timeout)`

Create a client. Uses [valuehead.ai](https://valuehead.ai) by default.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str` | required | Your API key (starts with `vh_`) |
| `base_url` | `str` | `https://valuehead-production.up.railway.app` | API base URL |
| `timeout` | `float` | `30.0` | HTTP request timeout in seconds |

Supports context manager:

```python
with ValueHead(api_key="vh_...") as client:
    result = client.submit(messages=[...])
```

### `client.submit(messages, metadata) -> SubmitResult`

Submit a structured trace for async evaluation. Returns immediately.

### `client.submit_text(text, context, metadata, first_speaker_role) -> SubmitResult`

Submit a raw text transcript. Returns immediately.

### `client.submit_voice(file_path, metadata, human_speaker, speakers_expected, first_speaker_role) -> SubmitResult`

Submit an audio file. Returns immediately.

### `client.wait(session_id, poll_interval, timeout) -> SessionDetail`

Poll until evaluation completes or fails. Default timeout is 300 seconds.

### `client.get(session_id) -> SessionDetail`

Get full session state including all judgements.

### `client.list(limit, offset) -> SessionsListResponse`

List your evaluation sessions, most recent first.

### `client.delete(session_id)`

Delete a session and its results.

## Response models

### `SubmitResult`

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Unique session identifier |
| `status` | `str` | `"pending"` — evaluation hasn't started yet |

### `SessionDetail`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Session ID |
| `status` | `str` | `pending` / `running` / `completed` / `failed` |
| `total_turns` | `int` | Number of conversation turns |
| `judgements` | `dict[str, TurnJudgement]` | Per-turn judgements keyed by turn number |
| `trajectory` | `TrajectoryJudgement | None` | Overall conversation assessment |
| `summary` | `ScoreSummary` | Aggregated score counts |
| `error` | `str | None` | Error message if evaluation failed |
| `metadata` | `dict` | Your metadata tags |

### `TurnJudgement`

| Field | Type | Description |
|-------|------|-------------|
| `turn` | `int` | Turn number (1-indexed) |
| `score` | `int` | `-1` (harmful), `0` (neutral), `1` (helpful) |
| `turn_reasoning` | `str` | Chain-of-thought reasoning for the score |
| `user_summary` | `str` | Summary of what the user said/asked |
| `assistant_summary` | `str` | Summary of the assistant's response |
| `tool_calls` | `list[ToolCallJudgement]` | Individual tool call evaluations |

### `ToolCallJudgement`

| Field | Type | Description |
|-------|------|-------------|
| `score` | `int` | `-1`, `0`, or `1` |
| `summary` | `str` | What the tool call did |
| `reasoning` | `str` | Why this score was assigned |
| `call_content` | `str` | The tool call content |

### `TrajectoryJudgement`

| Field | Type | Description |
|-------|------|-------------|
| `score` | `int` | Overall conversation score (`-1`, `0`, `1`) |
| `reasoning` | `str` | Why this overall score was given |
| `completed` | `bool` | Did the conversation reach its goal? |
| `early_termination` | `bool` | Did the user cut the conversation short? |
| `failures` | `list[TrajectoryFailure]` | Specific failure points identified |

### `ScoreSummary`

| Field | Type | Description |
|-------|------|-------------|
| `total_turns` | `int` | Total turns in the conversation |
| `judged_turns` | `int` | Number of turns evaluated so far |
| `helpful` | `int` | Count of +1 scores |
| `neutral` | `int` | Count of 0 scores |
| `harmful` | `int` | Count of -1 scores |
| `net_score` | `int` | Trajectory score (or sum of turn scores) |
| `trajectory_score` | `int | None` | Overall trajectory score if available |

## Evaluation rubric

Every turn is evaluated on these dimensions:

| Dimension | What it catches |
|-----------|----------------|
| **Hallucination** | Fabricated information not grounded in context or tool outputs |
| **Wrong tool usage** | Inappropriate tool selection, wrong parameters, or off-topic responses |
| **Inconsistent reasoning** | Contradicts prior steps, available evidence, or stated plan |
| **Unnecessary actions** | Redundant tool calls, verbose responses, or wasted steps |
| **Safety** | Harmful, biased, or inappropriate content |

Each dimension includes dedicated chain-of-thought reasoning. The final score synthesizes all dimensions.

The trajectory-level assessment evaluates the conversation as a whole: did the agent achieve the user's goal? Were there failure points? Did the user give up?

## REST API

You can also use the API directly without the SDK.

### Authentication

Every request requires either:
- `X-Api-Key: vh_your_key` header (recommended for programmatic use)
- `Authorization: Bearer <jwt_token>` header (from login)

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/traces` | Submit a conversation trace (async) |
| `POST` | `/api/v1/traces/voice` | Submit a voice recording |
| `POST` | `/api/v1/traces/text` | Submit a raw text transcript |
| `POST` | `/api/v1/traces/batch` | Submit multiple traces |
| `GET` | `/api/v1/traces/{id}` | Get session + judgements |
| `GET` | `/api/v1/traces/{id}/stream` | SSE stream of live judgements |
| `POST` | `/api/v1/traces/{id}/evaluate` | Synchronous evaluation (blocks) |
| `GET` | `/api/v1/traces` | List sessions (paginated) |
| `DELETE` | `/api/v1/traces/{id}` | Delete a session |
| `DELETE` | `/api/v1/traces` | Delete all sessions |
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Get JWT token |
| `GET` | `/api/v1/auth/me` | Get profile |
| `POST` | `/api/v1/auth/rotate-key` | Rotate API key |

### Example: curl

```bash
# Submit a trace
curl -X POST https://valuehead-production.up.railway.app/api/v1/traces \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: vh_your_key" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello"},
      {"role": "assistant", "content": "Hi! How can I help you today?"}
    ]
  }'

# Get results
curl https://valuehead-production.up.railway.app/api/v1/traces/{session_id} \
  -H "X-Api-Key: vh_your_key"
```

### SSE streaming

Stream judgements as they are produced, one per turn:

```bash
curl -N https://valuehead-production.up.railway.app/api/v1/traces/{session_id}/stream \
  -H "X-Api-Key: vh_your_key"
```

Events:
- `judgement` — emitted after each turn is judged, contains the turn's judgement data
- `done` — evaluation is complete

## Dashboard

The web dashboard at [valuehead.ai](https://valuehead.ai) provides:

- **Trace list** — all your evaluated conversations with status, score bars, and metadata tags
- **Trace detail** — per-turn breakdown with expandable reasoning, tool call scores, and trajectory assessment
- **Live streaming** — watch judgements appear in real-time as turns are evaluated
- **Score visualizations** — donut charts and score bars showing helpful/neutral/harmful distribution
- **Settings** — manage your API key, view your profile
- **Admin dashboard** — (admin users) view all users, trace counts, system stats, and manage accounts

## Limits

| Limit | Default |
|-------|---------|
| Traces per user | 200 |
| Tool calls per trace | 100 |
| Characters per trace | 500,000 |

## Errors

The SDK raises typed exceptions:

| Exception | When |
|-----------|------|
| `AuthenticationError` | Invalid or missing API key (401/403) |
| `NotFoundError` | Session not found (404) |
| `EvaluationTimeoutError` | `wait()` exceeded its timeout |
| `ValueHeadError` | Any other API error |

```python
from valuehead import ValueHead, AuthenticationError, EvaluationTimeoutError

try:
    session = client.wait(result.session_id, timeout=60)
except EvaluationTimeoutError:
    print("Still evaluating, check back later")
    session = client.get(result.session_id)
```

## Self-hosting

ValueHead can be self-hosted. See the [main repository](https://github.com/Aradhye2002/valuehead-sdk) for setup instructions.

```bash
git clone https://github.com/Aradhye2002/valuehead-sdk.git
cd valuehead
cp .env.example .env  # add your OpenAI API key
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py
```

Point the SDK to your instance:

```python
client = ValueHead(api_key="vh_...", base_url="http://localhost:8000")
```

### Environment variables (self-hosted)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRACE_OBS_LLM_API_KEY` | Yes | — | OpenAI API key for the judge LLM |
| `TRACE_OBS_LLM_BASE_URL` | No | `https://api.openai.com/v1` | Any OpenAI-compatible API |
| `TRACE_OBS_LLM_MODEL` | No | `gpt-5.4-mini` | Judge model ID |
| `TRACE_OBS_JUDGE_TEMPERATURE` | No | `0.6` | Judge temperature |
| `TRACE_OBS_ELEVENLABS_API_KEY` | For voice | — | ElevenLabs API key (speech-to-text) |
| `TRACE_OBS_DATABASE_URL` | No | SQLite | Database URL (supports Postgres) |
| `TRACE_OBS_JWT_SECRET` | Production | `change-me-...` | JWT signing secret |
| `TRACE_OBS_ADMIN_EMAILS` | No | `[]` | Emails auto-granted admin role |
| `TRACE_OBS_MAX_TRACES_PER_USER` | No | `200` | Per-user trace limit |
| `TRACE_OBS_MAX_TOOL_CALLS_PER_TRACE` | No | `100` | Max tool calls per trace |
| `TRACE_OBS_MAX_TRACE_CHARS` | No | `500000` | Max characters per trace |

## License

MIT
