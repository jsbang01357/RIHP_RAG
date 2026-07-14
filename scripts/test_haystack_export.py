#!/usr/bin/env python3
"""Haystack 문서가 기존 RIHP 청크·출처와 1:1로 연결되는지 검사한다."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    chunks = load_jsonl(ROOT / "rag" / "chunks.jsonl")
    documents = load_jsonl(ROOT / "rag" / "haystack_documents.jsonl")
    with (ROOT / "sources" / "manifest.csv").open(encoding="utf-8") as stream:
        source_ids = {row["source_id"] for row in csv.DictReader(stream)}

    assert len(documents) == len(chunks) == 1_846
    assert [item["id"] for item in documents] == sorted(item["id"] for item in chunks)
    assert len({item["id"] for item in documents}) == len(documents)
    assert all(set(item) == {"id", "content", "meta"} for item in documents)
    assert all(str(item["content"]).strip() for item in documents)
    assert all(item["meta"]["source_id"] in source_ids for item in documents)
    assert all(str(item["meta"]["publication_title"]).strip() for item in documents)
    assert all(isinstance(item["meta"]["pdf_page"], int) for item in documents)
    assert all(
        urlparse(str(item["meta"]["source_url"])).hostname == "rihp.re.kr"
        for item in documents
    )
    print("OK: Haystack 문서 1,846개 · RIHP 출처·PDF 페이지 연결 검증 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
