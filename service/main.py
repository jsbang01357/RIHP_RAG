"""RIHP Policy Finder Cloud Run 웹·RAG API."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from service.rag_service import HybridRagService


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
LOGGER = logging.getLogger(__name__)
app = FastAPI(title="RIHP Policy Finder API", version="2.0.0")


class RagRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=6, ge=1, le=8)


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self.lock:
            entries = self.requests[client]
            while entries and entries[0] < cutoff:
                entries.popleft()
            if len(entries) >= self.limit:
                return False
            entries.append(now)
            return True


rate_limiter = InMemoryRateLimiter(
    limit=int(os.getenv("RAG_RATE_LIMIT", "12")),
    window_seconds=int(os.getenv("RAG_RATE_WINDOW_SECONDS", "600")),
)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@lru_cache(maxsize=1)
def rag_service() -> HybridRagService:
    return HybridRagService()


@app.get("/api/health")
def health() -> dict[str, object]:
    service = rag_service()
    return {
        "status": "ok",
        "service": "rihp-rag",
        "haystack_documents": service.document_count,
        "embeddings_ready": service.embeddings_ready,
        "generation_enabled": service.generator is not None,
    }


@app.post("/api/rag")
async def rag(payload: RagRequest, request: Request) -> dict[str, object]:
    if not rate_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="잠시 후 다시 질문해 주세요.")
    try:
        return await run_in_threadpool(rag_service().answer, payload.query.strip(), payload.top_k)
    except Exception as error:
        LOGGER.exception("RIHP RAG request failed")
        raise HTTPException(status_code=503, detail="RAG 검색을 완료하지 못했습니다.") from error


app.mount("/", StaticFiles(directory=SITE, html=True), name="site")
