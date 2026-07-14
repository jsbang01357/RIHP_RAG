#!/usr/bin/env python3
"""Vertex 다국어 임베딩을 재개 가능하게 생성한다."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from service.gcp_clients import VertexEmbeddingClient


DEFAULT_DOCUMENTS = ROOT / "rag" / "haystack_documents.jsonl"
DEFAULT_OUTPUT = ROOT / "rag" / "haystack_embeddings.jsonl"
DEFAULT_CHECKPOINT = ROOT / "rag" / ".haystack_embeddings.checkpoint.jsonl"


def load_lines(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    documents = load_lines(args.documents)
    if args.limit is not None:
        documents = documents[: args.limit]
    completed = {
        str(item["id"]): item
        for item in [*load_lines(args.output), *load_lines(args.checkpoint)]
    }
    pending = [item for item in documents if str(item["id"]) not in completed]
    client = VertexEmbeddingClient()
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    with args.checkpoint.open("a", encoding="utf-8") as checkpoint:
        for offset in range(0, len(pending), args.batch_size):
            batch = pending[offset : offset + args.batch_size]
            for attempt in range(args.retries):
                try:
                    embeddings = client.embed_many(
                        [str(item["content"]) for item in batch],
                        "RETRIEVAL_DOCUMENT",
                    )
                    break
                except Exception:
                    if attempt + 1 == args.retries:
                        raise
                    time.sleep(2**attempt)
            for item, embedding in zip(batch, embeddings, strict=True):
                record = {
                    "id": item["id"],
                    "model": client.model,
                    "dimensions": client.dimensions,
                    "embedding": embedding,
                }
                completed[str(item["id"])] = record
                checkpoint.write(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
            checkpoint.flush()
            print(f"{min(offset + len(batch), len(pending)):,}/{len(pending):,}", flush=True)

    ordered = [completed[str(item["id"])] for item in documents]
    args.output.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in ordered
        ),
        encoding="utf-8",
    )
    if len(ordered) == len(load_lines(args.documents)) and args.checkpoint.exists():
        args.checkpoint.unlink()
    print(json.dumps({"documents": len(ordered), "model": client.model, "dimensions": client.dimensions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
