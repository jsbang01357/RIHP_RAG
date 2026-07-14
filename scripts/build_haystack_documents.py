#!/usr/bin/env python3
"""RIHP 범용 청크를 Haystack Document JSONL로 변환한다."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS = ROOT / "rag" / "chunks.jsonl"
DEFAULT_MANIFEST = ROOT / "sources" / "manifest.csv"
DEFAULT_OUTPUT = ROOT / "rag" / "haystack_documents.jsonl"


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return {row["source_id"]: row for row in csv.DictReader(stream)}


def build_documents(chunks_path: Path, manifest_path: Path) -> list[dict[str, object]]:
    manifest = load_manifest(manifest_path)
    documents: list[dict[str, object]] = []
    with chunks_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            chunk = json.loads(line)
            metadata = chunk["metadata"]
            source = manifest[metadata["source_id"]]
            content = str(chunk["text"]).strip()
            if not content:
                continue
            documents.append(
                {
                    "id": chunk["id"],
                    "content": content,
                    "meta": {
                        "source_id": metadata["source_id"],
                        "unit_id": metadata["unit_id"],
                        "section_title": metadata["title"],
                        "publication_title": source.get("title") or metadata["title"],
                        "collection": metadata["collection"],
                        "publication_id": metadata["publication_id"],
                        "year": source.get("year", ""),
                        "published_at": metadata.get("published_at") or source.get("published_at", ""),
                        "pdf_page": int(metadata["pdf_page"]),
                        "authors": metadata.get("authors", []),
                        "topics": metadata.get("topics", []),
                        "source_url": metadata.get("source_url") or source.get("source_url", ""),
                        "review_status": metadata.get("review_status", ""),
                    },
                }
            )
    documents.sort(key=lambda item: str(item["id"]))
    return documents


def main() -> int:
    documents = build_documents(DEFAULT_CHUNKS, DEFAULT_MANIFEST)
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(
        "".join(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
            for document in documents
        ),
        encoding="utf-8",
    )
    print(json.dumps({"haystack_documents": len(documents)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
