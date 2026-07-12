# RIHP Policy Knowledge Base

의료정책연구원(RIHP) 공개 발간물을 출처 추적 가능한 Markdown 지식베이스와
재생성 가능한 RAG 코퍼스로 정리하는 비상업적 파일럿입니다.

## 설계 원칙

- 원본 PDF와 사람이 읽는 Markdown을 분리합니다.
- 계간지는 기사 단위, 연구·정책 보고서는 장 단위로 나눕니다.
- 모든 본문은 PDF 물리 페이지를 보존합니다.
- AI 요약과 기관의 공식 견해를 혼동하지 않습니다.
- 콘텐츠 권리와 코드 라이선스를 분리합니다.
- 벡터 DB나 특정 AI 공급자에 종속되지 않습니다.

## 폴더

- `content/`: 사람이 읽는 정규화 Markdown
- `wiki/topics/`: 주제별 진입점과 문서 연결
- `rag/chunks.jsonl`: 검색·임베딩용 재생성 산출물
- `sources/manifest.csv`: 원본 식별자, 해시, 페이지 수
- `qa/extraction-report.csv`: 손상, 빈 페이지, 표, 중복 글자 검사
- `scripts/`: 변환 및 검증 코드
- `site/`: 브라우저 안에서 동작하는 정적 키워드 검색 사이트
- `tasks/`: 작업 기록과 교훈

원본 PDF는 저장소 최상위 또는 외부 경로에 둘 수 있지만 Git에는 포함하지 않습니다.

## 파일럿 빌드

Codex 번들 Python을 사용하는 예시입니다.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/sync_latest.py --dry-run
python3 scripts/sync_latest.py
python3 scripts/build_corpus.py
python3 scripts/build_site.py
python3 scripts/build_exports.py
python3 scripts/build_corpus.py --input /path/to/document.pdf
python3 scripts/test_build_corpus.py
python3 scripts/test_sync_latest.py
python3 scripts/test_exports.py
python3 scripts/test_site.py
```

인자를 생략하면 저장소 아래의 PDF를 재귀적으로 찾습니다. 여러 `--input`을 함께
사용할 수 있습니다. 산출물은 입력 PDF에서 언제든 다시 만들 수 있습니다.

`scripts/sync_latest.py`는 RIHP 공식 게시판 첫 페이지를 최신순으로 읽고, 아직 없는
연구보고서·정책현안/이슈브리핑·계간지·연례보고서를 공식 첨부 링크에서 내려받습니다.
기본 배치는 연구보고서 6건, 정책현안/이슈브리핑 3건, 계간지 2건, 연례보고서 1건이며
각 `--research`, `--policy`, `--forum`, `--annual` 인자로 조절할 수 있습니다.

현재 로컬 파일럿 PDF는 `sources/pdfs/`와 저장소 최상위에 있으며 `.gitignore`로
Git 커밋에서 제외됩니다.

## 정적 검색 사이트

`site/index.html`은 `site/search-index.json`을 불러와 서버나 외부 API 없이
브라우저에서 검색합니다. 검색 결과에는 본문 발췌, 저자, PDF 물리 페이지와
RIHP 공식 게시판·글번호가 표시됩니다. 직접 PDF 버튼은 RIHP의 외부 접속 제한으로
안정적이지 않아 노출하지 않습니다.

검색 인덱스는 배포 전에 `scripts/build_site.py`로 다시 생성하고
ChatGPT용 분할 TXT와 `rihp-rag-chatgpt.zip`은 `scripts/build_exports.py`로 생성합니다.
`scripts/test_exports.py`와 `scripts/test_site.py`가 청크 누락, PDF 혼입, RIHP 링크와
로컬 경로 누출을 검사합니다. 생성 ZIP은 Git 이력에는 넣지 않고 Pages 빌드 산출물로만 제공합니다.

RIHP는 외부 사이트에서 게시판 상세 URL로 바로 이동하면 홈페이지로 되돌리는 정책을
사용합니다. 버튼에는 검증된 공식 게시판과 글번호를 그대로 표시해 출처 위치를 확인할
수 있게 했으며, 이 동작은 RIHP 서버 정책이 변경되면 함께 재검증합니다.

## Cloudflare Pages 배포

정적 사이트는 Cloudflare Pages 프로젝트 `rihp-rag`에 배포합니다.

```bash
python3 scripts/build_site.py
python3 scripts/build_exports.py
python3 scripts/test_exports.py
python3 scripts/test_site.py
npx wrangler pages deploy site --project-name rihp-rag --branch main
```

- 기본 주소: `https://rihp-rag.pages.dev`
- 운영 주소: `https://rihp.jisong.dev`

GitHub Actions는 빌드와 검증만 수행하며 GitHub Pages 배포에는 사용하지 않습니다.

## 품질 상태

현재 생성되는 본문은 `machine-extracted-needs-review` 상태입니다. 다음 항목은 사람의
확인이 끝나기 전 공식 배포본으로 간주하지 않습니다.

- 표와 병합 셀
- 그림 안의 텍스트
- 큰 제목의 중복 글자
- 기사 또는 장의 경계
- 저자명, 발행일, 기관 공식 견해 여부

## 권리

코드와 콘텐츠의 권리 범위는 다릅니다. 공개 저장소로 전환하기 전에 `RIGHTS.md`를
확인하고 권리자의 서면 허락 범위를 기록해야 합니다.
