"""Haystack BM25와 Vertex 의미 검색을 결합한 RIHP 정책 RAG."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from haystack import Document, Pipeline, component
from haystack.components.joiners import DocumentJoiner
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever, InMemoryEmbeddingRetriever
from haystack.document_stores.in_memory import InMemoryDocumentStore

from service.gcp_clients import QwenMaaSGenerator, VertexEmbeddingClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENTS = ROOT / "rag" / "haystack_documents.jsonl"
DEFAULT_EMBEDDINGS = ROOT / "rag" / "haystack_embeddings.jsonl"
LOGGER = logging.getLogger(__name__)
SYSTEM_PROMPT = """당신은 의료정책 자료 탐색 도우미입니다.
제공된 의료정책연구원 공개 발간물의 기계 추출 본문만 근거로 답하십시오.
문서에 적힌 내용과 당신의 해석을 구분하고, 근거가 부족하면 모른다고 답하십시오.
근거 본문에 명시되지 않은 수치, 사례, 원인, 전망을 추가하거나 수치를 임의로 환산하지 마십시오.
제공되지 않은 근거 번호를 만들지 말고, 각 사실은 실제로 뒷받침하는 번호에만 연결하십시오.
각 문단 끝에 반드시 [1]처럼 제공된 근거 번호를 표시하십시오.
발간물 또는 필자의 견해를 의료정책연구원의 공식 입장으로 단정하지 마십시오.
답변은 자연스러운 한국어로 작성하고 불필요한 한자 혼용을 피하십시오.
정책 판단이나 직접 인용 전에는 사용자가 연결된 RIHP 원문을 확인하도록 안내하십시오."""


@component
class VertexQueryEmbedder:
    def __init__(self, client: Any) -> None:
        self.client = client

    @component.output_types(embedding=list[float])
    def run(self, text: str) -> dict[str, list[float]]:
        return {"embedding": self.client.embed_query(text)}


def load_documents(
    documents_path: Path,
    embeddings_path: Path | None = None,
) -> tuple[list[Document], bool]:
    embedding_by_id: dict[str, list[float]] = {}
    if embeddings_path and embeddings_path.exists():
        for line in embeddings_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                embedding_by_id[str(item["id"])] = item["embedding"]

    documents: list[Document] = []
    for line in documents_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        documents.append(
            Document(
                id=item["id"],
                content=item["content"],
                meta=item["meta"],
                embedding=embedding_by_id.get(str(item["id"])),
            )
        )
    embeddings_ready = bool(documents) and len(embedding_by_id) == len(documents)
    return documents, embeddings_ready


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class HybridRagService:
    def __init__(
        self,
        documents_path: Path = DEFAULT_DOCUMENTS,
        embeddings_path: Path = DEFAULT_EMBEDDINGS,
        embedder: Any | None = None,
        generator: Any | None = None,
        generation_enabled: bool | None = None,
    ) -> None:
        documents, embeddings_ready = load_documents(documents_path, embeddings_path)
        if not documents:
            raise RuntimeError("Haystack 검색 문서가 없습니다.")
        self.documents = documents
        self.document_count = len(documents)
        self.embeddings_ready = embeddings_ready
        self.store = InMemoryDocumentStore(embedding_similarity_function="cosine")
        self.store.write_documents(documents)
        self.bm25 = InMemoryBM25Retriever(self.store, top_k=30, scale_score=True)
        self.pipeline: Pipeline | None = None

        if embeddings_ready:
            embedding_client = embedder or VertexEmbeddingClient()
            self.pipeline = Pipeline()
            self.pipeline.add_component("query_embedder", VertexQueryEmbedder(embedding_client))
            self.pipeline.add_component(
                "dense",
                InMemoryEmbeddingRetriever(self.store, top_k=30, scale_score=True),
            )
            self.pipeline.add_component("bm25", self.bm25)
            self.pipeline.add_component(
                "joiner",
                DocumentJoiner(
                    join_mode="reciprocal_rank_fusion",
                    weights=[0.72, 0.28],
                    top_k=30,
                ),
            )
            self.pipeline.connect("query_embedder.embedding", "dense.query_embedding")
            self.pipeline.connect("dense.documents", "joiner.documents")
            self.pipeline.connect("bm25.documents", "joiner.documents")

        enabled = generation_enabled
        if enabled is None:
            enabled = os.getenv("RAG_GENERATION_ENABLED", "true").lower() not in {"0", "false", "no"}
        self.generator = (generator or QwenMaaSGenerator()) if enabled else None

    def retrieve(self, query: str, top_k: int = 6) -> list[Document]:
        top_k = min(max(int(top_k), 1), 8)
        candidate_k = min(max(top_k * 5, 30), 80)
        if self.pipeline:
            result = self.pipeline.run(
                {
                    "query_embedder": {"text": query},
                    "dense": {"top_k": candidate_k},
                    "bm25": {"query": query, "top_k": candidate_k},
                    "joiner": {"top_k": candidate_k},
                }
            )
            candidates = result["joiner"]["documents"]
        else:
            candidates = self.bm25.run(query=query, top_k=candidate_k)["documents"]

        unique: list[Document] = []
        seen_pages: set[tuple[str, int]] = set()
        seen_text: set[str] = set()
        for document in candidates:
            page_key = (str(document.meta.get("source_id", "")), int(document.meta["pdf_page"]))
            fingerprint = normalized_text(str(document.content or ""))
            if page_key in seen_pages or fingerprint in seen_text:
                continue
            seen_pages.add(page_key)
            seen_text.add(fingerprint)
            unique.append(document)
            if len(unique) == top_k:
                break
        return unique

    @staticmethod
    def source_for(document: Document, index: int) -> dict[str, Any]:
        meta = document.meta
        authors = meta.get("authors") or []
        return {
            "index": index,
            "id": document.id,
            "publication_title": meta["publication_title"],
            "section_title": meta["section_title"],
            "collection": meta["collection"],
            "publication_id": meta["publication_id"],
            "published_at": meta.get("published_at") or meta.get("year") or "",
            "pdf_page": int(meta["pdf_page"]),
            "authors": authors,
            "content": normalized_text(str(document.content or "")),
            "score": document.score,
            "source_url": meta["source_url"],
        }

    @staticmethod
    def fallback_answer(sources: list[dict[str, Any]]) -> str:
        references = ", ".join(
            f'{source["publication_title"]} PDF {source["pdf_page"]}쪽 [{source["index"]}]'
            for source in sources[:3]
        )
        return f"관련 근거로 {references} 등을 찾았습니다. 아래 발간물과 RIHP 원문을 직접 확인해 주세요."

    def answer(self, query: str, top_k: int = 6) -> dict[str, Any]:
        documents = self.retrieve(query, top_k)
        sources = [self.source_for(document, index) for index, document in enumerate(documents, 1)]
        mode = "hybrid" if self.pipeline else "bm25"
        if not sources:
            return {
                "answer": "관련된 의료정책 근거를 찾지 못했습니다.",
                "sources": [],
                "mode": mode,
                "generation_status": "not_requested",
            }
        if self.generator is None:
            return {
                "answer": self.fallback_answer(sources),
                "sources": sources,
                "mode": mode,
                "generation_status": "disabled",
            }

        context = "\n\n".join(
            f'[{source["index"]}] {source["publication_title"]} · {source["section_title"]} '
            f'· PDF {source["pdf_page"]}쪽\n{source["content"]}'
            for source in sources
        )
        user_prompt = (
            f"질문: {query}\n\n근거 본문:\n{context}\n\n"
            "근거 본문에 명시된 사실만 사용해 한국어로 간결하게 답하고, "
            "서로 다른 관점이 있으면 구분해서 설명하세요. 계산이나 추정은 하지 마세요."
        )
        try:
            answer = self.generator.generate(SYSTEM_PROMPT, user_prompt)
            generation_status = "generated"
        except Exception:
            LOGGER.exception("Vertex generation failed; returning retrieval-only fallback")
            answer = self.fallback_answer(sources)
            generation_status = "unavailable"
        return {
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "generation_status": generation_status,
        }
