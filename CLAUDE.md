# 해커톤 FAQ 디스코드 봇 — 프로젝트 브리핑

> 이 문서는 Claude Code에서 작업을 이어가기 위한 인수인계 문서입니다.
> 프로젝트 폴더에 `CLAUDE.md`로 두면 Claude Code가 자동으로 읽습니다.

## 프로젝트 목적

해커톤에서 학생들이 자주 묻는 질문(일정, 장소, 와이파이, 제출 방법 등)에
자동으로 답해주는 디스코드 봇. 운영진이 노션에 정리한 내용을 지식으로 사용한다.

## 현재 구현 상태 (v1 — 완성, 동작 확인됨)

키워드 매칭 기반 FAQ 봇. Python 3.9+ / discord.py 2.3+.

| 파일 | 역할 |
|---|---|
| `bot.py` | 디스코드 봇 본체. 멘션 질문, `!질문`, `!주제`, `!리로드` 명령 처리 |
| `faq_engine.py` | `faq.md` 파싱 + 키워드 매칭 로직 (discord 의존성 없음, 단독 테스트 가능) |
| `faq.md` | FAQ 데이터. `## 주제 \| 키워드1, 키워드2` 헤더 + 답변 본문 형식 |
| `requirements.txt` | `discord.py>=2.3` |
| `README.md` | 봇 생성/초대/실행/노션 내용 넣는 법 안내 (운영진용) |

핵심 설계:
- `faq_engine.load_faq()` → `FaqEntry(title, keywords, answer)` 리스트
- `find_answer(question, entries)` → 질문 문자열을 정규화(소문자+공백제거) 후
  키워드 포함 여부로 스코어링 (매칭 개수, 매칭 길이 합). 없으면 `None`
- `bot.py`의 `build_reply(question)` 가 응답 생성의 단일 진입점.
  **답변 엔진을 업그레이드할 때 이 함수만 교체하면 됨** (의도된 설계)
- 토큰은 `DISCORD_TOKEN` 환경변수로 주입. 코드에 하드코딩 금지
- 디스코드 개발자 포털에서 MESSAGE CONTENT INTENT 필수

동작 확인: 파싱 8개 항목, "와이파이 비번 뭐예요?" → 와이파이,
"혼자 왔는데 팀 어떻게 구해요" → 팀 구성 등 매칭 테스트 통과.

## 다음 작업 후보 (우선순위 순)

### 1. Notion API 실시간 연동

현재는 노션 내용을 `faq.md`에 수동 복붙. 이를 Notion API로 자동화한다.

- 패키지: `notion-client` (공식 Python SDK)
- 준비물: https://www.notion.so/my-integrations 에서 Internal Integration 생성
  → `NOTION_TOKEN` 환경변수. 대상 노션 페이지에서 ⋯ → Connections → 해당 integration 연결
- 구현 방향:
  - `notion_sync.py` 신규 모듈: 지정한 페이지(들)의 블록을 읽어
    `faq.md`와 같은 구조(`FaqEntry` 리스트)로 변환
  - 노션 쪽 규칙: heading_2 블록을 "주제 | 키워드들"로, 그 아래 블록들을 답변으로 파싱
    (기존 faq.md 규칙과 동일한 컨벤션 유지)
  - `!리로드` 명령이 노션에서 다시 fetch하도록 확장 + 시작 시 1회 로드
  - 노션 API 장애 시 마지막 성공본을 로컬 캐시(`faq_cache.md`)로 폴백
- 페이지 ID는 `NOTION_PAGE_ID` 환경변수로

### 2. Claude API 연동 (자연어 답변)

키워드로 못 잡는 다양한 질문 표현에 대응.

- 패키지: `anthropic`
- `build_reply()` 교체: FAQ 전체(또는 키워드 매칭 상위 후보)를 컨텍스트로 넣고
  `claude-haiku-4-5` 모델에 질문 전달. 시스템 프롬프트에
  "제공된 자료에 없는 내용은 모른다고 답하고 운영진 문의 안내" 규칙 포함
- 비용 절감: 프롬프트 캐싱 사용 (FAQ 컨텍스트가 매 요청 동일하므로 효과 큼)
- `ANTHROPIC_API_KEY` 환경변수
- 폴백: API 오류 시 기존 키워드 매칭으로 답변

### 3. 소소한 개선 아이디어

- 답변 못 찾은 질문을 로그 파일로 남겨 운영진이 FAQ 보강에 활용
- 슬래시 커맨드(`/질문`)로 전환 (discord.py app_commands)
- 특정 채널(#질문)에서만 반응하도록 제한 옵션

## 주의사항

- `DISCORD_TOKEN`, `NOTION_TOKEN`, `ANTHROPIC_API_KEY`는 절대 커밋하지 말 것
  (`.env` + python-dotenv 도입 권장, `.gitignore`에 `.env` 추가)
- `faq_engine.py`는 discord 의존성이 없게 유지할 것 (테스트 용이성)
- 답변 엔진 교체 시에도 `!주제`, `!리로드` 명령은 유지
