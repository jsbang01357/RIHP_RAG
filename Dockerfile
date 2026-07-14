FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HAYSTACK_TELEMETRY_ENABLED=False \
    PORT=8080

WORKDIR /app
COPY requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt

COPY service ./service
COPY site ./site
COPY rag/haystack_documents.jsonl ./rag/haystack_documents.jsonl
COPY rag/haystack_embeddings.jsonl ./rag/haystack_embeddings.jsonl
COPY RIGHTS.md ./

CMD ["sh", "-c", "uvicorn service.main:app --host 0.0.0.0 --port ${PORT}"]
