# 해커톤 FAQ 디스코드 봇 🦁

학생들이 자주 묻는 질문에 자동으로 답해주는 키워드 기반 FAQ 봇입니다.
노션에 정리해둔 내용을 `faq.md`에 붙여넣기만 하면 됩니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `bot.py` | 봇 본체 (실행 파일) |
| `faq_engine.py` | faq.md를 읽고 키워드 매칭하는 로직 |
| `faq.md` | **질문/답변 데이터 — 여러분이 수정할 파일!** |
| `requirements.txt` | 필요한 패키지 목록 |

## 1. 디스코드 봇 만들기 (개발자 포털)

1. https://discord.com/developers/applications 접속 → **New Application** 클릭, 이름 입력 (예: `해커톤도우미`)
2. 왼쪽 메뉴 **Bot** 탭으로 이동
3. **Privileged Gateway Intents** 에서 ✅ **MESSAGE CONTENT INTENT** 를 반드시 켜주세요 (안 켜면 봇이 메시지를 못 읽어요)
4. **Reset Token** 을 눌러 토큰을 복사해 둡니다 (⚠️ 절대 깃허브 등에 올리지 마세요!)

## 2. 봇을 서버에 초대하기

1. 왼쪽 메뉴 **OAuth2 → URL Generator**
2. SCOPES에서 `bot` 체크
3. BOT PERMISSIONS에서 `Send Messages`, `Read Message History` 체크
4. 아래 생성된 URL을 브라우저에 붙여넣고 → 해커톤 서버 선택 → 승인

## 3. 실행하기

Python 3.9 이상이 필요합니다.

```bash
pip install -r requirements.txt

# 토큰 설정 — 아래 둘 중 편한 방법으로

# 방법 1) .env 파일 사용 (추천, 재부팅해도 다시 안 쳐도 됨)
# .env.example을 .env로 복사한 뒤 DISCORD_TOKEN= 뒤에 토큰 붙여넣기
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux

# 방법 2) 환경변수 직접 설정 (Mac/Linux)
export DISCORD_TOKEN="여기에_복사한_토큰"

# 방법 2) 환경변수 직접 설정 (Windows PowerShell)
$env:DISCORD_TOKEN="여기에_복사한_토큰"

python bot.py
```

⚠️ `.env` 파일은 `.gitignore`에 포함되어 있어 git에 커밋되지 않습니다. 그래도 실수로 `git add .env`를 하지 않도록 주의하세요.

터미널에 `✅ 로그인 성공: ...` 이 뜨면 성공!

## 4. 사용법 (학생들에게 공지할 내용)

- **@봇이름 와이파이 비번 뭐예요?** — 봇을 멘션하고 질문
- **!질문 제출 어떻게 해요?** — 명령어로 질문
- **!주제** — 봇이 답할 수 있는 주제 목록 보기
- **!리로드** — faq.md 수정 후 다시 불러오기 (서버 관리 권한 필요)

## 5. 노션 내용 넣는 법 ⭐

`faq.md`를 열어 아래 형식으로 추가하면 끝입니다.

```
## 주제이름 | 키워드1, 키워드2, 키워드3
답변 내용 (노션에서 복사해서 붙여넣기 OK, 여러 줄 가능)
```

- 노션에서 페이지 내용을 복사해 답변 부분에 붙여넣으세요.
  (노션 우측 상단 ⋯ → **Export → Markdown** 으로 내보내면 서식까지 그대로 가져올 수 있어요)
- **키워드는 학생들이 실제로 쓸 법한 단어**로 다양하게 넣을수록 잘 잡힙니다.
  예: `와이파이, wifi, 인터넷, 비번, 비밀번호`
- 수정한 뒤 디스코드에서 `!리로드` 를 입력하면 봇 재시작 없이 바로 반영됩니다.

## 6. 계속 켜두려면 (호스팅)

봇은 `python bot.py`가 실행 중일 때만 작동합니다.

- **행사 당일만 쓴다면**: 운영진 노트북에서 그냥 켜두는 게 제일 간단해요.
- **24시간 돌리려면**: Railway, Fly.io 같은 서비스나 AWS/GCP 무료 티어 서버에 올리면 됩니다.

## 자주 묻는 문제

- **봇이 아무 반응이 없어요** → MESSAGE CONTENT INTENT를 켰는지, 봇에게 채널 읽기/쓰기 권한이 있는지 확인
- **`DISCORD_TOKEN 환경변수가 없습니다`** → 위 3번의 토큰 설정을 다시 확인
- **질문을 못 알아들어요** → 해당 주제의 키워드에 그 표현을 추가하고 `!리로드`

## 나중에 더 똑똑하게 만들고 싶다면

키워드 매칭은 표현이 다르면 못 알아듣는 한계가 있어요.
학생 질문이 다양해지면 Claude API를 연동해 faq.md 내용을 근거로
자연어로 답하게 업그레이드할 수 있습니다 (구조상 `build_reply` 함수만 바꾸면 됨).
