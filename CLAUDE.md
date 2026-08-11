# 해커톤 FAQ 디스코드 봇 — 프로젝트 브리핑

> 이 문서는 Claude Code에서 작업을 이어가기 위한 인수인계 문서입니다.
> 프로젝트 폴더에 `CLAUDE.md`로 두면 Claude Code가 자동으로 읽습니다.

## 프로젝트 목적

해커톤에서 학생들이 자주 묻는 질문(일정, 장소, 와이파이, 제출 방법 등)에
자동으로 답해주는 디스코드 봇. 운영진이 노션에 정리한 내용을 지식으로 사용한다.

## 현재 구현 상태 (동작 확인됨)

Python 3.10+ / discord.py 2.3+. 키워드 매칭 → Claude 폴백의 2단 구조.

| 파일 | 역할 |
|---|---|
| `bot.py` | 봇 본체. 슬래시 커맨드 4개 + `!리로드` 처리 |
| `faq_engine.py` | `faq.md` 파싱 + 키워드 매칭 (discord 의존성 없음) |
| `claude_engine.py` | Claude 자연어 답변 (discord 의존성 없음) |
| `openai_engine.py` | OpenAI 자연어 답변 (claude_engine과 동일 인터페이스) |
| `llm.py` | LLM 백엔드 스위치 + 폴백 체인 (`LLM_PROVIDER` / `LLM_FALLBACK`) |
| `stats_engine.py` | 질문 로그 기록/집계 (discord 의존성 없음) |
| `digest.py` | 미답변 질문 분석 → 운영진 일일 리포트 (discord 의존성 없음) |
| `stats_cli.py` | 터미널에서 통계 확인 |
| `hours.py` | 질문 운영시간 판단 (discord 의존성 없음) |
| `paths.py` | 파일 경로 중앙 관리 (절대경로) |
| `faq.md` | FAQ 데이터. 현재 9개 카테고리 / 65개 항목 |
| `deploy/` | 오라클 서버 배포 세트 (systemd, setup.sh, update.sh, DEPLOY.md) |

### 핵심 설계

- `faq_engine.load_faq()` → `FaqEntry(title, keywords, answer, category)` 리스트
  - `# 카테고리` (해시 1개) = 구획용. 매칭엔 영향 없고 `/해커톤주제` 그룹핑에만 쓰임
  - `## 주제 | 키워드1, 키워드2` (해시 2개) = 실제 항목
- `find_answer()` — 정규화(소문자+공백제거) 후 키워드별 (일치도 × 키워드 길이) 합산.
  `MIN_SCORE=1.0` 미만이면 `None` 반환 → Claude 폴백으로 넘어감.
  `FUZZY_THRESHOLD=0.82`로 오타/변형도 일부 잡음
- **`bot.build_reply()`가 응답 생성의 단일 진입점.** 답변 엔진을 바꿀 땐 이 함수만
  교체하면 된다 (의도된 설계)
- `llm.py`는 스위치 + 폴백 체인. `LLM_PROVIDER` 실패 시 `LLM_FALLBACK`으로 넘김.
  두 엔진 모듈은 지연 import라 한쪽 패키지가 없어도 동작한다.
  `llm.last_used`에 **실제로 답한** 백엔드가 담기므로 통계는 이걸 기록해야 한다
  (`llm.PROVIDER`는 설정값일 뿐이라 폴백 시 틀린 값이 된다)
- OpenAI 모델명은 라인업이 자주 바뀐다. 코드에 못박지 말고 `OPENAI_MODEL`로 두고,
  모델명 오류 시 `models.list()`로 사용 가능 목록을 로그에 찍는다
- 질문/답변은 **항상 ephemeral**(본인에게만 보임). 공개 채팅 멘션·`!명령`에는
  안내 메시지(`NUDGE_MSG`)만 나감
- Claude 호출은 동기 함수라 `asyncio.to_thread`로 감싼다.
  안 그러면 API 응답을 기다리는 동안 봇 전체가 멈춘다
- 모든 경로는 `paths.py`에서 `__file__` 기준 절대경로로 계산.
  상대경로를 쓰면 systemd 실행 시 cwd가 `/`가 되어 faq.md를 못 찾는다

### 환경변수

필수는 `DISCORD_TOKEN` 하나. 나머지는 전부 선택.
전체 목록과 설명은 `.env.example` 참고. 코드에 토큰 하드코딩 금지.

디스코드 개발자 포털에서 **MESSAGE CONTENT INTENT** 필수.

## 배포

오라클 클라우드 Always Free VM + systemd. 절차는 `deploy/DEPLOY.md`.

- 서버 접속 후 `bash deploy/setup.sh` 하나로 설치 완료 (여러 번 실행해도 안전)
- 코드 갱신은 `bash deploy/update.sh`
- **서버리스 불가**: websocket 상시 연결이 필요하다 (`intents.message_content`, `on_message`)
- **인바운드 포트 불필요**: 아웃바운드만 쓰므로 Security List/iptables 손댈 것 없음
- Shape은 AMD Micro(1GB)로 충분. ARM은 "Out of capacity"로 잘 안 잡히는데
  이 봇엔 과할 정도의 사양이라 기다릴 이유가 없다

## 다음 작업 후보

### 1. Notion API 실시간 연동

현재는 노션 내용을 `faq.md`에 수동 복붙. 이를 Notion API로 자동화한다.

- 패키지: `notion-client`
- 준비물: https://www.notion.so/my-integrations 에서 Internal Integration 생성
  → `NOTION_TOKEN`. 대상 페이지에서 ⋯ → Connections → 해당 integration 연결
- 구현 방향:
  - `notion_sync.py` 신규 모듈: 지정 페이지의 블록을 `FaqEntry` 리스트로 변환
  - heading_2 블록을 "주제 | 키워드들"로, 그 아래 블록들을 답변으로 파싱
    (기존 faq.md 컨벤션 유지)
  - `!리로드`가 노션에서 다시 fetch하도록 확장 + 시작 시 1회 로드
  - 노션 API 장애 시 마지막 성공본을 `faq_cache.md`로 폴백
- 페이지 ID는 `NOTION_PAGE_ID` 환경변수로

### 2. 테스트 추가

`faq_engine` / `hours` / `stats_engine`은 discord 의존성이 없어 단독 테스트가 쉽다.
pytest로 매칭 정확도 회귀 테스트를 짜두면 키워드를 늘릴 때 안심할 수 있다.

### 3. 소소한 개선

- 특정 채널에서만 반응하도록 제한 옵션
- 답변에 "도움이 됐나요?" 반응 버튼 → 품질 지표 수집
- `/해커톤미답변` 슬래시 커맨드 (원할 때 즉시 리포트 조회, 관리자 전용)
- 미답변 리포트를 GitHub PR로 올려 diff로 검토하게 하기

## 주의사항

- `DISCORD_TOKEN`, `ANTHROPIC_API_KEY`는 절대 커밋 금지.
  `.env`는 `.gitignore`에 있고, `.env.example`은 값이 빈 채로 커밋한다
- `stats.log` / `unanswered.log`도 커밋 금지 (학생 질문 본문·사용자 ID 포함)
- `unanswered.log`는 `시각 / [처리주체] / 사용자ID / 질문` 4칸이다. 사용자ID가 없던
  시절의 3칸 줄도 남아 있을 수 있으므로 `digest._parse_line`은 둘 다 받는다.
  칸 수를 바꿀 땐 이 파서를 같이 고칠 것 — 형식이 안 맞는 줄은 조용히 버려져서
  리포트가 "미답변 0건"으로 나가고, 아무도 이상하다고 느끼지 못한다
- `faq_engine.py`, `hours.py`, `stats_engine.py`, `claude_engine.py`는
  **discord 의존성이 없게 유지할 것** (단독 테스트 가능해야 함)
- 답변 엔진을 교체해도 `/해커톤주제`, `!리로드` 명령은 유지
- 줄바꿈은 LF로 통일한다 (`.gitattributes`). 윈도우에서 CRLF로 저장되면
  git diff가 전체 파일 변경으로 잡히고, 리눅스에서 셸 스크립트가 실행되지 않는다
- 디스코드 메시지는 2000자 제한. `bot.clip()`으로 자르고 있으니 새 응답 경로를
  추가할 때도 통과시킬 것
- `digest.py`는 **제안만 하고 faq.md를 직접 고치지 않는다.** 잘못된 키워드 하나가
  조용히 오답을 만들기 때문 (`감점`이 노코드 항목에 들어가 "AI 안 쓰면 감점?"을
  가로챈 전례가 있다). 자동 반영 기능을 넣자는 요청이 오면 이 위험을 먼저 설명할 것
- 리포트에는 학생 질문 원문이 들어간다. `DIGEST_CHANNEL_ID`는 운영진 전용 채널이어야 함
- `on_ready`는 재접속마다 호출된다. 여기서 tasks 루프를 시작할 땐 `is_running()` 확인 필수
