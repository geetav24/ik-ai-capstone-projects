import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_loan_review(prompt: str) -> str:
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4.1-mini"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful AI loan review assistant. "
                    "Do not approve or reject loans. "
                    "Only identify missing documents, risk signals, "
                    "and next steps for a human reviewer."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content