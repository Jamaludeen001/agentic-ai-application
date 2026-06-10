def classify_intent(message: str, llm) -> str:
    messages = [
        {"role": "system", "content": """Classify into exactly one of:
- POSITIVE_FEEDBACK
- NEGATIVE_FEEDBACK
- CONTINUATION
Reply with ONLY the label."""},
        {"role": "user", "content": message},
    ]
    out    = llm.invoke(messages)
    intent = out.content.strip() if hasattr(out, "content") else str(out).strip()
    if intent not in ("POSITIVE_FEEDBACK", "NEGATIVE_FEEDBACK", "CONTINUATION"):
        return "CONTINUATION"
    return intent
