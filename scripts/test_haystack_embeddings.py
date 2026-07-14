#!/usr/bin/env python3
"""Vertex 임베딩이 Haystack 문서와 1:1로 정렬됐는지 검사한다."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "rag" / "haystack_documents.jsonl"
EMBEDDINGS = ROOT / "rag" / "haystack_embeddings.jsonl"


def load(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    documents = load(DOCUMENTS)
    embeddings = load(EMBEDDINGS)
    assert len(documents) == len(embeddings) == 1_846
    assert [item["id"] for item in documents] == [item["id"] for item in embeddings]
    assert {item["model"] for item in embeddings} == {"text-multilingual-embedding-002"}
    assert {item["dimensions"] for item in embeddings} == {256}
    for item in embeddings:
        vector = item["embedding"]
        assert isinstance(vector, list) and len(vector) == 256
        assert all(isinstance(value, (int, float)) for value in vector)
        assert any(abs(float(value)) > 1e-8 for value in vector)
    print("OK: Vertex 다국어 임베딩 1,846개 · 256차원 · 문서 ID 정렬 검증 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
