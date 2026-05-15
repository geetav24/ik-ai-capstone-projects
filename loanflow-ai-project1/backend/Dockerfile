FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# spaCy model — downloaded separately because it's not a standard PyPI package.
# en_core_web_sm (~12 MB) is sufficient for PII detection in guardrails.
# Swap for en_core_web_lg (~750 MB) if higher accuracy is needed in production.
RUN python -m spacy download en_core_web_sm

COPY app ./app

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]