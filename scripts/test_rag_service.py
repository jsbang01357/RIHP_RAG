#!/usr/bin/env python3
"""네트워크 없이 Haystack 하이브리드 검색·중복 제거·인용을 검사한다."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.rag_service import HybridRagService
from service.main import InMemoryRateLimiter


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0] if "지역" in text else [0.0, 1.0, 0.0]


class FakeGenerator:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "공식 입장" in system_prompt
        assert "임의로 환산" in system_prompt
        assert "계산이나 추정은 하지 마세요" in user_prompt
        assert "[1]" in user_prompt
        return "지역의료 정책 근거를 확인했습니다. [1]"


class FailingGenerator:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("temporary error")


def document(identifier: str, page: int, content: str, vector: list[float]) -> tuple[dict, dict]:
    item = {
        "id": identifier,
        "content": content,
        "meta": {
            "source_id": "report-1",
            "unit_id": "unit-1",
            "section_title": "지역의료 연구",
            "publication_title": "지역의료 정책 보고서",
            "collection": "research-report",
            "publication_id": "2026-01",
            "year": "2026",
            "published_at": "2026-01-01",
            "pdf_page": page,
            "authors": ["연구자"],
            "topics": ["regional-healthcare"],
            "source_url": "https://rihp.re.kr/bbs/board.php?bo_table=research_report&wr_id=1",
            "review_status": "machine-extracted-needs-review",
        },
    }
    return item, {"id": identifier, "embedding": vector}


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
    )


def main() -> int:
    records = [
        document("page-10-a", 10, "지역의료 접근성과 인력 배치 근거", [1.0, 0.0, 0.0]),
        document("page-10-b", 10, "지역의료 접근성을 설명하는 같은 페이지의 다른 청크", [0.9, 0.1, 0.0]),
        document("page-11", 11, "지역 의료기관과 필수의료 지원 방안", [0.8, 0.2, 0.0]),
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        docs_path = root / "documents.jsonl"
        embeddings_path = root / "embeddings.jsonl"
        write_jsonl(docs_path, [item[0] for item in records])
        write_jsonl(embeddings_path, [item[1] for item in records])
        service = HybridRagService(
            docs_path,
            embeddings_path,
            embedder=FakeEmbedder(),
            generator=FakeGenerator(),
        )
        result = service.answer("지역의료 인력 배치는 어떻게 해야 하나", 3)
        fallback_service = HybridRagService(
            docs_path,
            embeddings_path,
            embedder=FakeEmbedder(),
            generator=FailingGenerator(),
        )
        logging.disable(logging.CRITICAL)
        try:
            fallback = fallback_service.answer("지역의료", 3)
        finally:
            logging.disable(logging.NOTSET)

    assert service.embeddings_ready is True
    assert result["mode"] == "hybrid"
    assert result["generation_status"] == "generated"
    assert "[1]" in result["answer"]
    pages = [source["pdf_page"] for source in result["sources"]]
    assert len(pages) == len(set(pages)) == 2
    assert result["sources"][0]["source_url"].startswith("https://rihp.re.kr/")
    assert fallback["generation_status"] == "unavailable"
    assert "PDF" in fallback["answer"]
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client") is True
    assert limiter.allow("client") is True
    assert limiter.allow("client") is False
    print("OK: Haystack 하이브리드 검색 · 페이지 중복 제거 · Qwen 인용 경로 검증 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
