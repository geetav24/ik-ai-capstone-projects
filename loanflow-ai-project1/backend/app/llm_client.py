import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Check backend/.env")

client = OpenAI(api_key=api_key)


async def ask_llm(prompt: str) -> str:
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
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content