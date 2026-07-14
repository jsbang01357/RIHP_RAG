#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = ["index.html", "styles.css", "app.js", "search.mjs", "search-index.json", ".nojekyll"]
    for name in required:
        assert (ROOT / "site" / name).exists(), f"missing site/{name}"
    assert (ROOT / "site" / "downloads" / "rihp-rag-chatgpt.zip").exists()
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
    assert "./downloads/rihp-rag-chatgpt.zip" in html
    assert 'type="module"' in html
    assert 'from "./search.mjs"' in app
    assert "groupRankedResults" in app
    assert 'class="publication-card"' in app
    assert 'class="page-hit"' in app
    assert '"compositionstart"' in app
    assert '"compositionend"' in app
    assert 'class="sidebar"' in html
    assert 'data-view="archive"' in html
    assert 'data-view-panel="downloads"' in html
    assert "function setView" in app
    assert "RIHP ${board} #${recordId} 보기" in app
    assert 'research_report: "연구보고서"' in app
    assert "원문 PDF ↗" not in app
    assert 'rel="noopener noreferrer">RIHP' not in app

    payload = json.loads((ROOT / "site" / "search-index.json").read_text(encoding="utf-8"))
    items = payload["items"]
    assert items, "search index is empty"
    assert payload["stats"]["chunks"] == len(items)
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["text"].strip() for item in items)
    assert all(item["publication_title"].strip() for item in items)
    assert all(item["source_url"] and item["pdf_url"] for item in items)
    assert all(urlparse(item["source_url"]).hostname == "rihp.re.kr" for item in items)
    assert all(urlparse(item["pdf_url"]).hostname == "rihp.re.kr" for item in items)

    combined = json.dumps(payload, ensure_ascii=False)
    assert "/Users/jsbang/" not in combined
    print(payload["stats"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
