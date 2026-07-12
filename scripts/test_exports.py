#!/usr/bin/env python3

from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "site" / "downloads"


def main() -> int:
    zip_path = DOWNLOADS / "rihp-rag-chatgpt.zip"
    assert zip_path.exists(), "missing ChatGPT RAG ZIP"
    assert zip_path.stat().st_size < 512 * 1024 * 1024, "ZIP exceeds ChatGPT file limit"

    manifest = json.loads((DOWNLOADS / "manifest.json").read_text(encoding="utf-8"))
    expected_chunks = manifest["stats"]["chunks"]
    assert manifest["format"] == "rihp-rag-chatgpt-pack-v1"
    assert sum(part["chunks"] for part in manifest["parts"]) == expected_chunks
    assert all(part["characters"] < 1_000_000 for part in manifest["parts"])

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert "README_CHATGPT.md" in names
        assert "manifest.json" in names
        assert "rag/chunks.jsonl" in names
        assert "sources/manifest.csv" in names
        assert not any(name.lower().endswith(".pdf") for name in names)
        assert not any("/unknown/" in name for name in names)
        part_names = sorted(name for name in names if name.startswith("chatgpt/") and name.endswith(".txt"))
        assert len(part_names) == len(manifest["parts"])
        joined = "".join(archive.read(name).decode("utf-8") for name in part_names)
        assert joined.count("=== RIHP CHUNK ===") == expected_chunks
        assert "source_url: https://rihp.re.kr/" in joined
        assert "pdf_url: https://rihp.re.kr/" in joined

    print(
        {
            "zip_bytes": zip_path.stat().st_size,
            "parts": len(manifest["parts"]),
            "chunks": expected_chunks,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
