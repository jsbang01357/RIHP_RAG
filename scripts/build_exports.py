#!/usr/bin/env python3
"""Build a deterministic, ChatGPT-friendly downloadable RIHP RAG package."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "site" / "downloads"
MAX_PART_CHARS = 900_000
ZIP_NAME = "rihp-rag-chatgpt.zip"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def date_number(item: dict[str, object]) -> int:
    value = str(item.get("published_at") or item.get("year") or "")
    digits = "".join(character for character in value if character.isdigit())
    return int((digits + "0000")[:8] or 0)


def chunk_block(item: dict[str, object]) -> str:
    authors = ", ".join(str(author) for author in item.get("authors", [])) or "미확인"
    topics = ", ".join(str(topic) for topic in item.get("topics", [])) or "미분류"
    fields = [
        "=== RIHP CHUNK ===",
        f"chunk_id: {item['id']}",
        f"source_id: {item['source_id']}",
        f"title: {item['title']}",
        f"collection: {item['collection']}",
        f"publication_id: {item['publication_id']}",
        f"year: {item.get('year', '')}",
        f"published_at: {item.get('published_at', '')}",
        f"pdf_page: {item['pdf_page']}",
        f"authors: {authors}",
        f"topics: {topics}",
        f"source_url: {item['source_url']}",
        f"pdf_url: {item['pdf_url']}",
        "text:",
        str(item["text"]).strip(),
        "=== END CHUNK ===",
        "",
    ]
    return "\n".join(fields)


def split_blocks(blocks: list[str], limit: int = MAX_PART_CHARS) -> list[list[str]]:
    parts: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for block in blocks:
        if current and current_chars + len(block) > limit:
            parts.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += len(block)
    if current:
        parts.append(current)
    return parts


def readme_text(stats: dict[str, object], part_count: int, corpus_sha256: str) -> str:
    return f"""# RIHP RAG ChatGPT Pack

의료정책연구원 공개 발간물에서 기계 추출한 비공식 검색·참고용 패키지입니다.

## 구성

- 발간물: {stats['documents']}개
- 문서 단위: {stats['units']}개
- RAG 청크: {stats['chunks']}개
- ChatGPT 업로드용 TXT: {part_count}개
- 코퍼스 SHA-256: `{corpus_sha256}`

## ChatGPT에서 사용하는 방법

1. 이 ZIP 파일의 압축을 풉니다.
2. `chatgpt/` 폴더의 `rihp-rag-part-*.txt` 파일을 모두 ChatGPT 대화나 프로젝트에 업로드합니다.
3. 아래 예시 프롬프트로 질문합니다.

```text
업로드한 RIHP RAG 파일만을 우선 근거로 답변해 주세요.
답변의 각 핵심 주장마다 발간물 제목, PDF 물리 페이지, RIHP 게시물 링크를 표시하세요.
파일에 근거가 없으면 추정하지 말고 근거가 부족하다고 말해 주세요.
기계 추출 오류 가능성이 있으므로 중요한 인용은 연결된 원문 PDF 확인이 필요하다고 알려 주세요.
질문: [여기에 질문]
```

## 주의

- ZIP 자체보다 압축을 푼 TXT 파일을 업로드하는 방식을 권장합니다.
- 표, 그림, 병합 셀, 문서 경계는 기계 추출 과정에서 손실될 수 있습니다.
- 정책 판단과 정식 인용에는 반드시 `source_url` 또는 `pdf_url`의 RIHP 원문을 확인하세요.
- 원문 저작권은 각 저작자와 대한의사협회 의료정책연구원에 있습니다.
"""


def zip_write_bytes(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def main() -> int:
    search_path = ROOT / "site" / "search-index.json"
    payload = json.loads(search_path.read_text(encoding="utf-8"))
    stats = payload["stats"]
    items = sorted(
        payload["items"],
        key=lambda item: (
            -date_number(item),
            str(item["source_id"]),
            int(item["pdf_page"]),
            str(item["id"]),
        ),
    )
    blocks = [chunk_block(item) for item in items]
    split = split_blocks(blocks)

    if DOWNLOADS.exists():
        shutil.rmtree(DOWNLOADS)
    DOWNLOADS.mkdir(parents=True)

    corpus_bytes = (ROOT / "rag" / "chunks.jsonl").read_bytes()
    corpus_sha256 = sha256_bytes(corpus_bytes)
    readme = readme_text(stats, len(split), corpus_sha256)
    part_files: list[tuple[str, bytes, int]] = []
    for index, part_blocks in enumerate(split, 1):
        header = (
            "RIHP RAG CHATGPT UPLOAD FILE\n"
            f"part: {index}/{len(split)}\n"
            f"corpus_sha256: {corpus_sha256}\n"
            "instruction: Use source_url, pdf_url, and pdf_page when citing evidence.\n\n"
        )
        part_payload = (header + "".join(part_blocks)).encode("utf-8")
        part_files.append((f"chatgpt/rihp-rag-part-{index:02d}.txt", part_payload, len(part_blocks)))

    manifest = {
        "format": "rihp-rag-chatgpt-pack-v1",
        "corpus_sha256": corpus_sha256,
        "stats": stats,
        "parts": [
            {
                "path": name,
                "bytes": len(part_payload),
                "characters": len(part_payload.decode("utf-8")),
                "chunks": chunk_count,
                "sha256": sha256_bytes(part_payload),
            }
            for name, part_payload, chunk_count in part_files
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (DOWNLOADS / "README_CHATGPT.md").write_text(readme, encoding="utf-8")
    (DOWNLOADS / "manifest.json").write_bytes(manifest_bytes)

    zip_path = DOWNLOADS / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        zip_write_bytes(archive, "README_CHATGPT.md", readme.encode("utf-8"))
        zip_write_bytes(archive, "manifest.json", manifest_bytes)
        for name, part_payload, _ in part_files:
            zip_write_bytes(archive, name, part_payload)
        for relative in (
            Path("rag/chunks.jsonl"),
            Path("sources/manifest.csv"),
            Path("sources/source_urls.json"),
        ):
            zip_write_bytes(archive, relative.as_posix(), (ROOT / relative).read_bytes())
        for folder in ("content", "wiki"):
            for path in sorted((ROOT / folder).rglob("*")):
                relative = path.relative_to(ROOT)
                if (
                    path.is_file()
                    and path.suffix.lower() != ".pdf"
                    and "unknown" not in relative.parts
                ):
                    zip_write_bytes(archive, relative.as_posix(), path.read_bytes())

    print(
        json.dumps(
            {
                "zip": zip_path.name,
                "zip_bytes": zip_path.stat().st_size,
                "parts": len(part_files),
                "chunks": sum(chunk_count for _, _, chunk_count in part_files),
                "corpus_sha256": corpus_sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
