#!/usr/bin/env python3
"""Build a source-traceable Markdown and JSONL corpus from RIHP PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pdfplumber


MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP = 150

TOPIC_RULES = {
    "regional-healthcare": ("지역의료", ["지역", "거점의료", "책임의료", "공공의료", "방문진료"]),
    "physician-workforce": ("의사인력", ["의사 수", "의사인력", "근무시간", "의사편재", "전공의"]),
    "medical-education": ("의학교육", ["의학교육", "평생교육", "수련", "CPD", "CME"]),
    "health-insurance": ("건강보험·수가", ["건강보험", "수가", "급여", "검체", "보험"]),
    "ai-and-data": ("AI·보건의료데이터", ["인공지능", "CMS-HCC", "데이터", "머신러닝"]),
}


@dataclass
class DocumentMeta:
    source_id: str
    title: str
    collection: str
    publication_id: str
    year: str
    authors: list[str] = field(default_factory=list)


@dataclass
class Unit:
    unit_id: str
    title: str
    category: str
    authors: list[str]
    start_page: int
    end_page: int


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def ascii_slug(value: str) -> str:
    value = nfc(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "document"


def compact(value: str) -> str:
    value = nfc(value).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def clean_tripled_glyphs(value: str) -> str:
    """Collapse PDF title glyphs accidentally repeated at least three times."""
    return re.sub(r"([가-힣])\1{2,}", r"\1", value)


def clean_page_text(value: str) -> str:
    value = nfc(value).replace("\u00a0", " ")
    value = clean_tripled_glyphs(value)
    lines: list[str] = []
    for raw in value.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            lines.append("")
            continue
        if line in {"www.rihp.re.kr", "대한의사협회 의료정책연구원"}:
            continue
        line = re.sub(r"\(cid:\d+\)", "", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def infer_meta(path: Path, first_pages: list[str]) -> DocumentMeta:
    filename = nfc(path.name)
    first = clean_tripled_glyphs("\n".join(first_pages[:3]))
    publication_text = re.sub(r"(?<=\d)\s+(?=\d)", "", first)

    if "계간의료정책포럼" in filename or "의료정책포럼 Vol." in first:
        match = re.search(r"Vol\.(\d+)\s+No\.(\d+)", first, re.I)
        volume, issue = match.groups() if match else ("unknown", "unknown")
        year_match = re.search(r"(20\d{2})년", "\n".join(first_pages[:10]))
        year = year_match.group(1) if year_match else "unknown"
        pub_id = f"v{volume}-n{issue}"
        return DocumentMeta(
            source_id=f"rihp-forum-{year}-{pub_id}",
            title=f"계간의료정책포럼 제{volume}권 {issue}호",
            collection="medical-policy-forum",
            publication_id=pub_id,
            year=year,
        )

    match = re.search(r"정책현안분석\s*(20\d{2}-\d{2})", first)
    if match:
        publication_id = match.group(1)
        title_lines = [line.strip() for line in first.splitlines() if line.strip()]
        title = title_lines[1] if len(title_lines) > 1 else filename.rsplit(".pdf", 1)[0]
        authors: list[str] = []
        for line in first.splitlines():
            if "(" not in line:
                continue
            prefix = line.split("(", 1)[0]
            if ":" in prefix:
                prefix = prefix.rsplit(":", 1)[-1]
            candidate = re.sub(r"\s+", "", prefix)
            if re.fullmatch(r"[가-힣]{2,4}", candidate) and candidate not in authors:
                authors.append(candidate)
        return DocumentMeta(
            source_id=f"rihp-policy-analysis-{publication_id}",
            title=title,
            collection="policy-analysis",
            publication_id=publication_id,
            year=publication_id[:4],
            authors=authors,
        )

    match = re.search(
        r"(?:연\s*구\s*보\s*고\s*서\s*)?\s*(20\d{2})\s*-\s*(\d{2})",
        publication_text,
    )
    if match:
        publication_id = f"{match.group(1)}-{match.group(2)}"
        candidates = [line.strip() for line in first.splitlines() if line.strip()]
        title = next(
            (line for line in candidates if "분석" in line or "연구" in line and "보고서" not in line),
            filename.rsplit(".pdf", 1)[0],
        )
        authors = re.findall(r"(?:연 구 책 임 자|연 구 원)\s*:\s*([가-힣 ]{2,8})", first)
        return DocumentMeta(
            source_id=f"rihp-research-report-{publication_id}",
            title=title.strip(),
            collection="research-report",
            publication_id=publication_id,
            year=publication_id[:4],
            authors=[re.sub(r"\s+", "", item) for item in authors],
        )

    issue_match = re.search(r"이슈브리핑\s*\+?(\d+)호", filename)
    if issue_match:
        publication_id = issue_match.group(1)
        return DocumentMeta(
            source_id=f"rihp-issue-briefing-{publication_id}",
            title=filename.rsplit(".pdf", 1)[0],
            collection="issue-briefing",
            publication_id=publication_id,
            year="unknown",
        )

    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:10]
    return DocumentMeta(
        source_id=f"rihp-document-{digest}",
        title=filename.rsplit(".pdf", 1)[0],
        collection="other",
        publication_id=digest,
        year="unknown",
    )


def parse_forum_toc(toc_text: str) -> list[tuple[str, str, list[str]]]:
    current_category = "article"
    items: list[tuple[str, str, list[str]]] = []
    category_pattern = re.compile(r"^\d+\s+(.+)$")
    for raw in toc_text.splitlines():
        line = raw.strip()
        if not line or line in {"CONTENTS"} or line.startswith("의료정책포럼 Vol."):
            continue
        category_match = category_pattern.match(line)
        if category_match:
            current_category = category_match.group(1).strip()
            continue
        if " / " in line:
            title, author = line.rsplit(" / ", 1)
            items.append((title.strip(), current_category, [author.replace(" ", "").strip()]))
        elif line.startswith("-"):
            items.append((line.lstrip("- ").strip(), current_category, []))
    return items


def find_title_page(title: str, page_texts: list[str], start_at: int = 1) -> int | None:
    needle = compact(title)
    if not needle:
        return None
    short = needle[: min(len(needle), 28)]
    for page_no in range(max(start_at, 1), len(page_texts) + 1):
        haystack = compact(clean_tripled_glyphs(page_texts[page_no - 1]))
        if needle in haystack or (len(short) >= 12 and short in haystack):
            return page_no
    return None


def find_forum_title_page(
    title: str,
    authors: list[str],
    all_titles: list[str],
    page_texts: list[str],
    start_at: int = 2,
) -> int | None:
    """Find the article itself, not a section divider listing several titles."""
    needle = compact(title)
    title_needles = [compact(item) for item in all_titles]
    for page_no in range(max(start_at, 2), len(page_texts) + 1):
        haystack = compact(clean_tripled_glyphs(page_texts[page_no - 1]))
        short = needle[: min(len(needle), 28)]
        if needle not in haystack and not (len(short) >= 12 and short in haystack):
            continue
        if authors and not any(compact(author) in haystack for author in authors):
            continue
        listed_titles = sum(1 for item in title_needles if item and item[: min(len(item), 28)] in haystack)
        if listed_titles > 1 and len(clean_page_text(page_texts[page_no - 1])) < 400:
            continue
        return page_no
    return None


def extract_title_page_authors(page_text: str) -> list[str]:
    authors: list[str] = []
    for line in clean_page_text(page_text).splitlines()[:16]:
        candidate = re.sub(r"\s+", "", line)
        if " " in line and re.fullmatch(r"[가-힣]{2,4}", candidate) and candidate not in authors:
            authors.append(candidate)
    return authors


def forum_units(meta: DocumentMeta, pages: list[str]) -> list[Unit]:
    items = parse_forum_toc(pages[0] if pages else "")
    all_titles = [item[0] for item in items]
    located: list[tuple[str, str, list[str], int]] = []
    cursor = 2
    for title, category, authors in items:
        hit = find_forum_title_page(title, authors, all_titles, pages, cursor)
        if hit is None:
            hit = find_forum_title_page(title, authors, all_titles, pages, 2)
        if hit is not None:
            page_authors = extract_title_page_authors(pages[hit - 1])
            located.append((title, category, page_authors or authors, hit))
            cursor = hit

    unique: list[tuple[str, str, list[str], int]] = []
    seen: set[tuple[str, int]] = set()
    for item in located:
        key = (compact(item[0]), item[3])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    title_needles = [compact(title)[:28] for title in all_titles]
    divider_pages: list[int] = []
    for page_no, page in enumerate(pages, 1):
        haystack = compact(clean_tripled_glyphs(page))
        listed_titles = sum(1 for needle in title_needles if len(needle) >= 12 and needle in haystack)
        if listed_titles > 1 and len(clean_page_text(page)) < 400:
            divider_pages.append(page_no)

    units: list[Unit] = []
    for index, (title, category, authors, start) in enumerate(unique, 1):
        next_start = unique[index][3] if index < len(unique) else len(pages) + 1
        end = max(start, next_start - 1)
        first_blank = next(
            (page_no for page_no in range(start + 1, end + 1) if not pages[page_no - 1].strip()),
            None,
        )
        if first_blank is not None:
            end = max(start, first_blank - 1)
        first_divider = next((page_no for page_no in divider_pages if start < page_no <= end), None)
        if first_divider is not None:
            end = max(start, first_divider - 1)
        units.append(
            Unit(
                unit_id=f"{meta.source_id}-a{index:02d}",
                title=title,
                category=category,
                authors=authors,
                start_page=start,
                end_page=end,
            )
        )
    return units


def report_units(meta: DocumentMeta, pages: list[str]) -> list[Unit]:
    candidates: list[tuple[int, str]] = []
    seen_sections: set[str] = set()
    if meta.collection == "research-report":
        pattern = re.compile(r"^(제[1-9]\d*장)\s*[❙|:]?\s*(.+)$")
        scan_start = min(20, len(pages))
    else:
        pattern = re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\.\s*(.+)$")
        scan_start = min(5, len(pages))

    toc_titles: dict[str, str] = {}
    for page in pages[:scan_start]:
        for line in clean_page_text(page).splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            section_key = match.group(1)
            title_text = re.sub(r"[·.]{3,}.*$", "", match.group(2)).strip()
            title_text = re.sub(r"\s+\d+$", "", title_text).strip()
            if title_text:
                toc_titles.setdefault(section_key, f"{section_key}. {title_text}")

    for page_no, page in enumerate(pages, 1):
        if page_no <= scan_start:
            continue
        for line in clean_page_text(page).splitlines()[:18]:
            match = pattern.match(line.strip())
            if match:
                section_key = match.group(1)
                if section_key in seen_sections:
                    continue
                title = toc_titles.get(section_key, f"{match.group(1)}. {match.group(2).strip()}")
                if not candidates or candidates[-1][0] != page_no:
                    candidates.append((page_no, title))
                    seen_sections.add(section_key)
                break

    seen_labels: set[str] = set()
    for page_no, page in enumerate(pages, 1):
        if page_no <= scan_start:
            continue
        lines = [line.strip() for line in clean_page_text(page).splitlines()[:14]]
        for label in ("참고문헌", "부록"):
            if label in seen_labels:
                continue
            if any(line.replace(" ", "").startswith(label) for line in lines):
                if not any(existing_page == page_no for existing_page, _ in candidates):
                    candidates.append((page_no, label))
                    seen_labels.add(label)
                break

    candidates.sort(key=lambda item: item[0])
    deduped: list[tuple[int, str]] = []
    for page_no, title in candidates:
        if not deduped or deduped[-1][0] != page_no:
            deduped.append((page_no, title))

    if not deduped:
        deduped = [(1, meta.title)]

    units: list[Unit] = []
    for index, (start, title) in enumerate(deduped, 1):
        end = deduped[index][0] - 1 if index < len(deduped) else len(pages)
        units.append(
            Unit(
                unit_id=f"{meta.source_id}-s{index:02d}",
                title=title,
                category="chapter",
                authors=meta.authors,
                start_page=start,
                end_page=max(start, end),
            )
        )
    return units


def make_units(meta: DocumentMeta, pages: list[str]) -> list[Unit]:
    if meta.collection == "medical-policy-forum":
        units = forum_units(meta, pages)
        if units:
            return units
    return report_units(meta, pages)


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value, ensure_ascii=False) for value in values) + "]"


def unit_markdown(meta: DocumentMeta, unit: Unit, pages: list[str], digest: str, source_file: str) -> str:
    topics = match_topics(meta.title + " " + unit.title + " " + "\n".join(pages[unit.start_page - 1 : unit.end_page]))
    frontmatter = [
        "---",
        f"id: {unit.unit_id}",
        f"title: {json.dumps(unit.title, ensure_ascii=False)}",
        f"collection: {meta.collection}",
        f"publication_id: {meta.publication_id}",
        f"year: {meta.year}",
        f"category: {json.dumps(unit.category, ensure_ascii=False)}",
        f"authors: {yaml_list(unit.authors)}",
        f"topics: {yaml_list(topics)}",
        f"pdf_pages: {unit.start_page}-{unit.end_page}",
        f"source_file: {json.dumps(source_file, ensure_ascii=False)}",
        f"source_sha256: {digest}",
        "extraction_status: machine-extracted-needs-review",
        "ai_generated_metadata: true",
        "---",
        "",
        f"# {unit.title}",
        "",
        "> [!CAUTION] 기계 추출 파일럿입니다. 표·그림·문서 경계를 원본 PDF와 대조해야 합니다.",
        "> 원문의 필자 개인 견해 고지가 있는 경우 기관의 공식 견해로 해석하지 않습니다.",
        "",
        "## 출처",
        "",
        f"- 발간물: {meta.title}",
        f"- PDF 물리 페이지: {unit.start_page}-{unit.end_page}",
        f"- 원본 파일: `{source_file}`",
        "",
        "## 정규화 본문",
        "",
    ]
    body: list[str] = []
    for page_no in range(unit.start_page, unit.end_page + 1):
        text = clean_page_text(pages[page_no - 1])
        if not text:
            continue
        body.extend([f'<a id="page-{page_no}"></a>', "", f"### PDF p.{page_no}", "", text, ""])
    return "\n".join(frontmatter + body).rstrip() + "\n"


def match_topics(text: str) -> list[str]:
    folded = text.lower()
    matches: list[str] = []
    for slug, (_, keywords) in TOPIC_RULES.items():
        if any(keyword.lower() in folded for keyword in keywords):
            matches.append(slug)
    return matches


def chunk_text(text: str, limit: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if boundary > start + limit // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def discover_inputs(root: Path, explicit: Iterable[str]) -> list[Path]:
    found = {path.resolve() for path in root.rglob("*.pdf")}
    for value in explicit:
        path = Path(value).expanduser().resolve()
        if path.is_file():
            found.add(path)
    return sorted(found, key=lambda path: nfc(path.name))


def build(root: Path, inputs: list[Path]) -> int:
    manifest_rows: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []
    rag_rows: list[dict[str, object]] = []
    topic_links: dict[str, list[tuple[str, str]]] = {slug: [] for slug in TOPIC_RULES}

    for path in inputs:
        digest = ""
        try:
            digest = sha256(path)
            with pdfplumber.open(path) as pdf:
                raw_pages = [page.extract_text() or "" for page in pdf.pages]
        except Exception as exc:  # damaged, evicted, and partial downloads stay visible in QA
            source_id = f"failed-{hashlib.sha1(nfc(path.name).encode()).hexdigest()[:10]}"
            manifest_rows.append(
                {
                    "source_id": source_id,
                    "collection": "unknown",
                    "title": nfc(path.stem),
                    "publication_id": "",
                    "pages": "",
                    "bytes": path.stat().st_size,
                    "sha256": digest or "unavailable",
                    "source_file": nfc(path.name),
                    "status": "failed",
                }
            )
            qa_rows.append(
                {
                    "source_id": source_id,
                    "status": "failed",
                    "pages": "",
                    "text_chars": "",
                    "empty_pages": "",
                    "table_label_pages": "",
                    "repeated_glyph_pages": "",
                    "units": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        meta = infer_meta(path, raw_pages[:20])
        units = make_units(meta, raw_pages)
        output_dir = root / "content" / meta.collection / meta.year / meta.source_id
        output_dir.mkdir(parents=True, exist_ok=True)
        for generated in output_dir.glob("*.md"):
            if generated.name == "index.md" or re.match(r"\d{2,3}-rihp-", generated.name):
                generated.unlink()

        unit_index: list[tuple[Unit, Path]] = []
        for ordinal, unit in enumerate(units, 1):
            unit_path = output_dir / f"{ordinal:02d}-{ascii_slug(unit.unit_id)}.md"
            unit_path.write_text(
                unit_markdown(meta, unit, raw_pages, digest, nfc(path.name)),
                encoding="utf-8",
            )
            relative = unit_path.relative_to(root)
            unit_index.append((unit, relative))

            unit_text = "\n".join(
                clean_page_text(raw_pages[page_no - 1])
                for page_no in range(unit.start_page, unit.end_page + 1)
            )
            for page_no in range(unit.start_page, unit.end_page + 1):
                page_text = clean_page_text(raw_pages[page_no - 1])
                for chunk_no, text in enumerate(chunk_text(page_text), 1):
                    rag_rows.append(
                        {
                            "id": f"{unit.unit_id}-p{page_no:03d}-c{chunk_no:02d}",
                            "text": text,
                            "metadata": {
                                "source_id": meta.source_id,
                                "unit_id": unit.unit_id,
                                "title": unit.title,
                                "collection": meta.collection,
                                "publication_id": meta.publication_id,
                                "pdf_page": page_no,
                                "authors": unit.authors,
                                "topics": match_topics(meta.title + " " + unit.title + " " + unit_text[:4000]),
                                "source_sha256": digest,
                                "source_file": nfc(path.name),
                                "review_status": "machine-extracted-needs-review",
                            },
                        }
                    )

            for topic in match_topics(meta.title + " " + unit.title + " " + unit_text[:5000]):
                topic_links[topic].append((unit.title, relative.as_posix()))

        index_lines = [
            "---",
            f"id: {meta.source_id}",
            f"title: {json.dumps(meta.title, ensure_ascii=False)}",
            f"collection: {meta.collection}",
            f"publication_id: {meta.publication_id}",
            f"year: {meta.year}",
            f"source_sha256: {digest}",
            "---",
            "",
            f"# {meta.title}",
            "",
            f"- 원본: `{nfc(path.name)}`",
            f"- PDF 페이지: {len(raw_pages)}",
            f"- 분할 문서: {len(units)}",
            "- 상태: 기계 추출 후 검수 필요",
            "",
            "## 문서 목록",
            "",
        ]
        for unit, relative in unit_index:
            index_lines.append(
                f"- [{unit.title}]({relative.name}) - PDF p.{unit.start_page}-{unit.end_page}"
            )
        (output_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        empty_pages = [str(i) for i, text in enumerate(raw_pages, 1) if not text.strip()]
        table_pages = [
            str(i)
            for i, text in enumerate(raw_pages, 1)
            if re.search(r"(?:표|Table)\s*[0-9ⅠⅡⅢIV]", text, re.I)
        ]
        repeated_pages = [
            str(i)
            for i, text in enumerate(raw_pages, 1)
            if re.search(r"([가-힣])\1{2,}", nfc(text))
        ]
        manifest_rows.append(
            {
                "source_id": meta.source_id,
                "collection": meta.collection,
                "title": meta.title,
                "publication_id": meta.publication_id,
                "pages": len(raw_pages),
                "bytes": path.stat().st_size,
                "sha256": digest,
                "source_file": nfc(path.name),
                "status": "extracted-needs-review",
            }
        )
        qa_rows.append(
            {
                "source_id": meta.source_id,
                "status": "extracted-needs-review",
                "pages": len(raw_pages),
                "text_chars": sum(len(text) for text in raw_pages),
                "empty_pages": ";".join(empty_pages),
                "table_label_pages": ";".join(table_pages),
                "repeated_glyph_pages": ";".join(repeated_pages),
                "units": len(units),
                "error": "",
            }
        )

    write_csv(
        root / "sources" / "manifest.csv",
        ["source_id", "collection", "title", "publication_id", "pages", "bytes", "sha256", "source_file", "status"],
        manifest_rows,
    )
    write_csv(
        root / "qa" / "extraction-report.csv",
        ["source_id", "status", "pages", "text_chars", "empty_pages", "table_label_pages", "repeated_glyph_pages", "units", "error"],
        qa_rows,
    )

    rag_path = root / "rag" / "chunks.jsonl"
    rag_path.parent.mkdir(parents=True, exist_ok=True)
    with rag_path.open("w", encoding="utf-8") as stream:
        for row in rag_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    wiki_root = root / "wiki" / "topics"
    wiki_root.mkdir(parents=True, exist_ok=True)
    for slug, (label, _) in TOPIC_RULES.items():
        lines = [f"# {label}", "", "> AI 규칙 기반 초안 인덱스입니다. 공개 전 사람 검수가 필요합니다.", ""]
        for title, relative in sorted(set(topic_links[slug])):
            target = "../../" + relative
            lines.append(f"- [{title}]({target})")
        if len(lines) == 4:
            lines.append("- 연결된 문서 없음")
        (wiki_root / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "inputs": len(inputs),
                "extracted": sum(row["status"] != "failed" for row in manifest_rows),
                "failed": sum(row["status"] == "failed" for row in manifest_rows),
                "units": sum(int(row["units"]) for row in qa_rows),
                "rag_chunks": len(rag_rows),
            },
            ensure_ascii=False,
        )
    )
    return 0 if any(row["status"] != "failed" for row in manifest_rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", default=[], help="PDF path; repeatable")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = discover_inputs(root, args.input)
    if not inputs:
        print("No PDF inputs found", file=sys.stderr)
        return 2
    return build(root, inputs)


if __name__ == "__main__":
    raise SystemExit(main())
