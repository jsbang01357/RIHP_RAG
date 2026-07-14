# RIHP Policy Knowledge Base

의료정책연구원(RIHP) 공개 발간물을 출처 추적 가능한 Markdown 지식베이스와
재생성 가능한 RAG 코퍼스로 정리하고, Haystack 하이브리드 검색으로 서비스하는
비상업적 파일럿입니다.

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
- `rag/haystack_documents.jsonl`: Cloud Run 검색용 Haystack 문서
- `rag/haystack_embeddings.jsonl`: Vertex 256차원 문서 임베딩
- `sources/manifest.csv`: 원본 식별자, 해시, 페이지 수
- `qa/extraction-report.csv`: 손상, 빈 페이지, 표, 중복 글자 검사
- `scripts/`: 변환 및 검증 코드
- `service/`: FastAPI·Haystack 하이브리드 RAG API
- `site/`: 브라우저 본문 검색과 RAG 답변 화면
- `deploy/`: GCP 리소스·Cloud Run 배포 스크립트
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
python3 scripts/build_haystack_documents.py
python3 scripts/build_corpus.py --input /path/to/document.pdf
python3 scripts/test_build_corpus.py
python3 scripts/test_sync_latest.py
python3 scripts/test_exports.py
python3 scripts/test_site.py
python3 scripts/test_haystack_export.py
HAYSTACK_TELEMETRY_ENABLED=False python3 scripts/test_rag_service.py
node scripts/test_web_runtime.mjs
```

인자를 생략하면 저장소 아래의 PDF를 재귀적으로 찾습니다. 여러 `--input`을 함께
사용할 수 있습니다. 산출물은 입력 PDF에서 언제든 다시 만들 수 있습니다.

`scripts/sync_latest.py`는 RIHP 공식 게시판 첫 페이지를 최신순으로 읽고, 아직 없는
연구보고서·정책현안/이슈브리핑·계간지·연례보고서를 공식 첨부 링크에서 내려받습니다.
기본 배치는 연구보고서 6건, 정책현안/이슈브리핑 3건, 계간지 2건, 연례보고서 1건이며
각 `--research`, `--policy`, `--forum`, `--annual` 인자로 조절할 수 있습니다.

현재 로컬 파일럿 PDF는 `sources/pdfs/`와 저장소 최상위에 있으며 `.gitignore`로
Git 커밋에서 제외됩니다.

## 검색과 Haystack RAG

`site/index.html`은 `site/search-index.json`을 불러와 브라우저에서 PDF 본문을
정확히 검색합니다. 결과는 발간물 단위로 묶고, 발간물 안에서
중복 페이지를 제거한 뒤 관련 문장, 저자, PDF 물리 페이지와 RIHP 공식
게시판·글번호를 표시합니다. 직접 PDF 버튼은 RIHP의 외부 접속 제한으로 안정적이지
않아 노출하지 않습니다.

질문형 검색은 Cloud Run의 Haystack 서비스가 처리합니다. BM25와 Vertex
`text-multilingual-embedding-002` 256차원 의미 검색을 reciprocal rank fusion으로
결합하고, 같은 발간물·PDF 페이지를 한 번만 남깁니다. Qwen3-Next 80B는 검색된
본문만 근거로 답하고 문단마다 `[1]` 형태의 근거 번호를 붙입니다. 생성 모델에 장애가
있어도 관련 발간물과 PDF 페이지는 반환합니다.

문서 임베딩은 코퍼스가 바뀔 때 한 번 생성해 컨테이너에 포함하고, 운영 요청에서는
질의 임베딩만 Vertex에 요청합니다.

```bash
python3 scripts/build_haystack_documents.py
python3 scripts/build_haystack_embeddings.py
python3 scripts/test_haystack_embeddings.py
```

검색 인덱스는 배포 전에 `scripts/build_site.py`로 다시 생성하고
ChatGPT용 분할 TXT와 `rihp-rag-chatgpt.zip`은 `scripts/build_exports.py`로 생성합니다.
`scripts/test_exports.py`와 `scripts/test_site.py`가 청크 누락, PDF 혼입, RIHP 링크와
로컬 경로 누출을 검사합니다. 생성 ZIP은 Git 이력에는 넣지 않고 Pages 빌드 산출물로만 제공합니다.

RIHP는 외부 사이트에서 게시판 상세 URL로 바로 이동하면 홈페이지로 되돌리는 정책을
사용합니다. 버튼에는 검증된 공식 게시판과 글번호를 그대로 표시해 출처 위치를 확인할
수 있게 했으며, 이 동작은 RIHP 서버 정책이 변경되면 함께 재검증합니다.

## GCP 운영 구조

- Cloud Run `rihp-rag` (`asia-northeast1`): FastAPI, 정적 사이트, Haystack RAG
- Vertex AI: 질의 임베딩과 Qwen3-Next 80B 근거 답변
- Artifact Registry `rihp-rag`: Cloud Run 컨테이너
- 서비스 계정 `rihp-rag-runtime`: Vertex AI 호출 전용

Cloud Run은 최소 인스턴스 0, 최대 인스턴스 2로 제한합니다. 답변은 700토큰으로
제한하고 인스턴스별 요청 빈도 제한을 두어 공개 API의 과도한 비용 발생을 줄입니다.

```bash
./deploy/gcp.sh all
```

- 목표 운영 주소: `https://rihp.jisong.dev`
- 검증된 Cloud Run 주소: `https://rihp-rag-1097794617970.asia-northeast1.run.app`
- Cloud Run 서비스: `rihp-rag` / `jisong-cloud-492111`

커스텀 도메인 인증서를 발급하려면 Cloudflare DNS에서 `rihp` CNAME을
`ghs.googlehosted.com`으로 바꾸고 프록시를 끈 DNS 전용 상태로 둡니다. 인증서가
활성화되기 전까지 기존 `rihp-rag.pages.dev` 배포는 삭제하지 않습니다.

## 비상 정적 배포

Cloudflare Pages는 AI 답변 API에 장애가 생겼을 때도 브라우저 본문 검색을 유지하는
비상 정적 배포로 남깁니다.

```bash
python3 scripts/build_site.py
python3 scripts/build_exports.py
python3 scripts/test_exports.py
python3 scripts/test_site.py
npx wrangler pages deploy site --project-name rihp-rag --branch main
```

- 비상 주소: `https://rihp-rag.pages.dev`

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
