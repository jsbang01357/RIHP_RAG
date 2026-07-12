#!/usr/bin/env python3
"""Download the latest missing RIHP PDFs and update source URL metadata."""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://rihp.re.kr"
USER_AGENT = "Mozilla/5.0 (compatible; RIHP-RAG/1.0; source-linked research archive)"


@dataclass(frozen=True)
class ListingItem:
    board: str
    wr_id: int
    title: str
    source_url: str


@dataclass(frozen=True)
class Detail:
    title: str
    published_at: str
    pdf_url: str
    pdf_name: str


BOARD_LIMITS = {
    "research_report": 6,
    "policy_analysis": 3,
    "publication_forum": 2,
    "annual": 1,
}


def strip_markup(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_listing(markup: str, board: str) -> list[ListingItem]:
    pattern = re.compile(
        rf'<a\b[^>]*href="([^"]*bo_table={re.escape(board)}[^"#]*wr_id=\d+[^"#]*)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    ordered_ids: list[int] = []
    by_id: dict[int, ListingItem] = {}
    for raw_url, raw_title in pattern.findall(markup):
        source_url = html.unescape(raw_url)
        query = parse_qs(urlparse(source_url).query)
        try:
            wr_id = int(query["wr_id"][0])
        except (KeyError, ValueError, IndexError):
            continue
        title = strip_markup(raw_title)
        canonical = f"{BASE_URL}/bbs/board.php?bo_table={board}&wr_id={wr_id}"
        if wr_id not in by_id:
            ordered_ids.append(wr_id)
            by_id[wr_id] = ListingItem(board, wr_id, title, canonical)
        elif len(title) > len(by_id[wr_id].title):
            by_id[wr_id] = ListingItem(board, wr_id, title, canonical)
    return [by_id[wr_id] for wr_id in ordered_ids if by_id[wr_id].title]


def parse_detail(markup: str) -> Detail:
    title_match = re.search(
        r'<h2\b[^>]*id="bo_v_title"[^>]*>(.*?)</h2>', markup, re.I | re.S
    )
    title = strip_markup(title_match.group(1)) if title_match else ""
    if not title:
        title_tag = re.search(r"<title>(.*?)</title>", markup, re.I | re.S)
        title = strip_markup(title_tag.group(1)).split(" > ", 1)[0] if title_tag else ""

    date_match = re.search(r'class="if_date"[^>]*>.*?(\d{2})-(\d{2})-(\d{2})', markup, re.I | re.S)
    published_at = ""
    if date_match:
        year, month, day = date_match.groups()
        published_at = f"20{year}-{month}-{day}"

    links = re.findall(
        r'<a\b[^>]*href="([^"]*download\.php[^"]*)"[^>]*class="[^"]*view_file_download[^"]*"[^>]*>(.*?)</a>',
        markup,
        re.I | re.S,
    )
    pdf_url = ""
    pdf_name = ""
    for raw_url, body in links:
        candidate_name = strip_markup(body)
        if ".pdf" in candidate_name.lower():
            pdf_url = html.unescape(raw_url)
            pdf_name = candidate_name
            break
    if not pdf_url and links:
        pdf_url = html.unescape(links[0][0])
        pdf_name = strip_markup(links[0][1])
    return Detail(title=title, published_at=published_at, pdf_url=pdf_url, pdf_name=pdf_name)


def source_id_from_title(title: str, board: str, published_at: str) -> str:
    match = re.search(r"연구\s*보고서\s*(20\d{2})\s*-\s*(\d{2})", title)
    if match:
        return f"rihp-research-report-{match.group(1)}-{match.group(2)}"
    match = re.search(r"정책\s*현안\s*분석\s*(20\d{2})\s*-\s*(\d{2})", title)
    if match:
        return f"rihp-policy-analysis-{match.group(1)}-{match.group(2)}"
    match = re.search(r"이슈\s*브리핑\s*(?:제\s*)?(\d+)\s*호", title)
    if match:
        return f"rihp-issue-briefing-{match.group(1)}"
    match = re.search(r"계간\s*의료정책포럼\s*제\s*(\d+)\s*권\s*(\d+)\s*호", title)
    if match:
        year = published_at[:4] if published_at else "unknown"
        return f"rihp-forum-{year}-v{match.group(1)}-n{match.group(2)}"
    match = re.search(r"(20\d{2})\s*(?:년\s*)?연례\s*보고서", title)
    if match:
        return f"rihp-annual-report-{match.group(1)}"
    raise ValueError(f"지원하지 않는 RIHP 발간물 제목입니다: {board}: {title}")


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/"})
    context = ssl.create_default_context()
    # RIHP currently serves a legacy DH key rejected by OpenSSL's default
    # security level. Certificate and hostname verification remain enabled.
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    with urlopen(request, timeout=60, context=context) as response:
        return response.read()


def existing_record_ids(source_urls: dict[str, dict[str, object]]) -> set[tuple[str, int]]:
    records: set[tuple[str, int]] = set()
    for item in source_urls.values():
        source_url = str(item.get("source_url", ""))
        query = parse_qs(urlparse(source_url).query)
        board = query.get("bo_table", [""])[0]
        try:
            wr_id = int(query.get("wr_id", [""])[0])
        except ValueError:
            continue
        if board:
            records.add((board, wr_id))
    return records


def select_items(
    listings: dict[str, list[ListingItem]],
    limits: dict[str, int],
    known: set[tuple[str, int]],
) -> list[ListingItem]:
    selected: list[ListingItem] = []
    for board, limit in limits.items():
        if limit <= 0:
            continue
        count = 0
        for item in listings.get(board, []):
            if (board, item.wr_id) in known:
                continue
            if board == "annual" and not re.search(r"20\d{2}\s*(?:년\s*)?연례\s*보고서", item.title):
                continue
            selected.append(item)
            count += 1
            if count >= limit:
                break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--research", type=int, default=BOARD_LIMITS["research_report"])
    parser.add_argument("--policy", type=int, default=BOARD_LIMITS["policy_analysis"])
    parser.add_argument("--forum", type=int, default=BOARD_LIMITS["publication_forum"])
    parser.add_argument("--annual", type=int, default=BOARD_LIMITS["annual"])
    args = parser.parse_args()

    limits = {
        "research_report": max(0, args.research),
        "policy_analysis": max(0, args.policy),
        "publication_forum": max(0, args.forum),
        "annual": max(0, args.annual),
    }
    source_urls_path = ROOT / "sources" / "source_urls.json"
    source_urls: dict[str, dict[str, object]] = (
        json.loads(source_urls_path.read_text(encoding="utf-8")) if source_urls_path.exists() else {}
    )
    for metadata in source_urls.values():
        published_at = str(metadata.get("published_at", ""))
        if not metadata.get("year") and re.match(r"20\d{2}-\d{2}-\d{2}", published_at):
            metadata["year"] = published_at[:4]
    known = existing_record_ids(source_urls)
    listings: dict[str, list[ListingItem]] = {}
    for board in limits:
        url = f"{BASE_URL}/bbs/board.php?bo_table={board}&page=1"
        listings[board] = parse_listing(fetch(url).decode("utf-8", errors="replace"), board)

    selected = select_items(listings, limits, known)
    if args.dry_run:
        print(json.dumps([item.__dict__ for item in selected], ensure_ascii=False, indent=2))
        return 0

    pdf_root = ROOT / "sources" / "pdfs"
    pdf_root.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for item in selected:
        try:
            detail = parse_detail(fetch(item.source_url).decode("utf-8", errors="replace"))
            if not detail.pdf_url:
                raise ValueError("PDF 첨부 링크가 없습니다")
            source_id = source_id_from_title(detail.title or item.title, item.board, detail.published_at)
            target = pdf_root / f"{source_id}.pdf"
            if args.refresh or not target.exists():
                payload = fetch(detail.pdf_url)
                if not payload.startswith(b"%PDF-"):
                    raise ValueError(f"PDF가 아닌 응답입니다 ({len(payload)} bytes)")
                partial = target.with_suffix(".pdf.part")
                partial.write_bytes(payload)
                partial.replace(target)
            year_match = re.search(r"20\d{2}", source_id)
            year = year_match.group(0) if year_match else detail.published_at[:4]
            source_urls[source_id] = {
                "source_url": item.source_url,
                "pdf_url": detail.pdf_url,
                "year": year,
                "board": item.board,
                "wr_id": item.wr_id,
                "published_at": detail.published_at,
                "title": detail.title or item.title,
            }
            downloaded.append(
                {
                    "source_id": source_id,
                    "title": detail.title or item.title,
                    "published_at": detail.published_at,
                    "bytes": target.stat().st_size,
                }
            )
        except Exception as exc:
            failures.append({"board": item.board, "wr_id": item.wr_id, "error": str(exc)})

    source_urls_path.write_text(
        json.dumps(dict(sorted(source_urls.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"downloaded": downloaded, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
