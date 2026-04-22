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

## Custom evaluation instructions

You can pass custom `instructions` to tailor the trajectory-level evaluation to your specific criteria. These instructions are factored heavily into the overall trajectory score.

```python
result = client.submit(
    messages=[...],
    instructions="Penalize any response where the agent does not cite a source. "
                 "The agent must never refuse to answer a question.",
)
```

This works with all submission methods:

```python
# Voice
result = client.submit_voice(
    "call.ogg",
    instructions="The agent should always confirm the customer's identity before making changes.",
)

# Text
result = client.submit_text(
    text="...",
    instructions="Focus on whether the agent resolved the issue in a single interaction.",
)
```

Use this to encode your own quality bar — e.g. "no incorrect tool calls", "must apologize for errors", "final answer must include a summary", etc.

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

## License

MIT
