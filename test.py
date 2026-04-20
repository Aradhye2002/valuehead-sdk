from valuehead import ValueHead

client = ValueHead(api_key="vh_b576afdb7ee1ab93e838d4a6a8fa2afb3467ee2627350f786b6b7516", base_url="http://localhost:8000")

# # Multi-turn trace
# result = client.submit(messages=[...], metadata={...})
# session = client.wait(result.session_id)

# Voice recording
result = client.submit_voice("../recording-3.opus", speakers_expected=2, first_speaker_role="assistant")
session = client.wait(result.session_id)

# # Raw text
# result = client.submit_text(
#     text="raw transcript...",
#     context="customer support call",
# )
# session = client.wait(result.session_id)

# Results
print(session.total_turns, session.summary.net_score)
for turn_num, j in session.judgements.items():
    score_s = f"+{j.score}" if j.score > 0 else str(j.score)
    tools = f" [{len(j.tool_calls)} tools]" if j.tool_calls else ""
    print(f"Turn {j.turn}: {score_s}{tools} — {j.user_summary}")
    print(f"  Asst: {j.assistant_summary}")
    print(f"  Reasoning: {j.turn_reasoning[:120]}")
