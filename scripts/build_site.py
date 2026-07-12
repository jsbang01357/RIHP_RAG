#!/usr/bin/env python3
"""Build the browser search index consumed by the static search site."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest_path = ROOT / "sources" / "manifest.csv"
    chunks_path = ROOT / "rag" / "chunks.jsonl"
    output_path = ROOT / "site" / "search-index.json"

    with manifest_path.open(encoding="utf-8") as stream:
        manifest = {row["source_id"]: row for row in csv.DictReader(stream)}

    items: list[dict[str, object]] = []
    unit_ids: set[str] = set()
    with chunks_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            chunk = json.loads(line)
            metadata = chunk["metadata"]
            source = manifest[metadata["source_id"]]
            unit_ids.add(metadata["unit_id"])
            items.append(
                {
                    "id": chunk["id"],
                    "unit_id": metadata["unit_id"],
                    "source_id": metadata["source_id"],
                    "title": metadata["title"],
                    "collection": metadata["collection"],
                    "publication_id": metadata["publication_id"],
                    "year": source.get("year", ""),
                    "published_at": metadata.get("published_at") or source.get("published_at", ""),
                    "pdf_page": metadata["pdf_page"],
                    "authors": metadata.get("authors", []),
                    "topics": metadata.get("topics", []),
                    "text": chunk["text"],
                    "source_url": metadata.get("source_url") or source.get("source_url", ""),
                    "pdf_url": metadata.get("pdf_url") or source.get("pdf_url", ""),
                    "review_status": metadata.get("review_status", ""),
                }
            )

    items.sort(key=lambda item: str(item["id"]))
    extracted_sources = [row for row in manifest.values() if row.get("status") != "failed"]
    payload = {
        "stats": {
            "documents": len(extracted_sources),
            "units": len(unit_ids),
            "chunks": len(items),
        },
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
