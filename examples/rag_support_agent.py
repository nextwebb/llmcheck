from __future__ import annotations

from openai import OpenAI

from llmcheck import add_context, add_tags, flag, instrument_openai


class FakeRetriever:
    def search(self, query: str) -> list[dict[str, str]]:
        return [
            {
                "id": "policy-1",
                "text": "Refunds above $100 require manager approval and take 3-5 business days.",
            }
        ]


client = instrument_openai(OpenAI())
retriever = FakeRetriever()


def answer_user(query: str, session_id: str = "demo-session") -> str:
    docs = retriever.search(query)
    add_context(docs)
    add_tags({"session_id": session_id})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a support agent."},
            {"role": "user", "content": query},
        ],
    )
    text = response.choices[0].message.content
    if "instant" in text.lower():
        flag(reason="claimed instant refund")
    return text
