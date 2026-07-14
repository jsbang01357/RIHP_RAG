"""Cloud Run ADC를 사용하는 Vertex AI 임베딩·생성 클라이언트."""

from __future__ import annotations

import os
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class VertexEmbeddingClient:
    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        session: Any | None = None,
    ) -> None:
        credentials, detected_project = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT") or detected_project
        if not self.project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT를 확인할 수 없습니다.")
        self.location = location or os.getenv("VERTEX_EMBEDDING_LOCATION", "us-central1")
        self.model = model or os.getenv("VERTEX_EMBEDDING_MODEL", "text-multilingual-embedding-002")
        self.dimensions = dimensions or int(os.getenv("VERTEX_EMBEDDING_DIMENSIONS", "256"))
        self.session = session or AuthorizedSession(credentials)
        self.url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project}"
            f"/locations/{self.location}/publishers/google/models/{self.model}:predict"
        )

    def embed_many(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        response = self.session.post(
            self.url,
            json={
                "instances": [{"content": text, "task_type": task_type} for text in texts],
                "parameters": {"outputDimensionality": self.dimensions, "autoTruncate": True},
            },
            timeout=90,
        )
        response.raise_for_status()
        predictions = response.json().get("predictions", [])
        embeddings = [item.get("embeddings", {}).get("values") for item in predictions]
        if len(embeddings) != len(texts) or any(not isinstance(item, list) for item in embeddings):
            raise RuntimeError("Vertex 임베딩 응답 수 또는 형식이 올바르지 않습니다.")
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_many([text], "RETRIEVAL_QUERY")[0]


class QwenMaaSGenerator:
    DEFAULT_MODEL = "qwen/qwen3-next-80b-a3b-instruct-maas"

    def __init__(self, project: str | None = None, session: Any | None = None) -> None:
        credentials, detected_project = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT") or detected_project
        if not self.project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT를 확인할 수 없습니다.")
        self.model = os.getenv("VERTEX_GENERATION_MODEL", self.DEFAULT_MODEL)
        self.max_tokens = int(os.getenv("RAG_MAX_TOKENS", "700"))
        self.session = session or AuthorizedSession(credentials)
        self.url = (
            f"https://aiplatform.googleapis.com/v1/projects/{self.project}/locations/global"
            "/endpoints/openapi/chat/completions"
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.session.post(
            self.url,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": self.max_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        if not choices:
            raise RuntimeError("Qwen 응답에 choices가 없습니다.")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Qwen 응답 본문이 없습니다.")
        return content.strip()
