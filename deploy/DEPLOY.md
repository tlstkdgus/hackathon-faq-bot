# 오라클 클라우드에 봇 배포하기

내 컴퓨터를 꺼도 봇이 계속 돌아가게 만드는 방법입니다.
오라클 클라우드 **Always Free** 서버를 씁니다 — 기한 없이 무료입니다.

전체 소요 시간: 대략 30~40분 (대부분 오라클 가입 절차)

---

## 왜 오라클인가 (그리고 왜 서버리스는 안 되는가)

이 봇은 디스코드에 **websocket으로 계속 연결**된 채로 메시지를 기다립니다
(`bot.py`의 `intents.message_content = True` + `on_message`).
그래서 요청이 올 때만 잠깐 깨어나는 방식(Cloudflare Workers, AWS Lambda 등)은
쓸 수 없고, **24시간 켜져 있는 서버**가 필요합니다.

반대로 좋은 소식도 있습니다. 이 봇은 **바깥에서 들어오는 접속을 받지 않습니다.**
디스코드와 Claude API로 나가기만 하죠. 그래서 방화벽 포트를 열 필요가 전혀 없습니다.
(오라클 배포에서 제일 많이 막히는 지점인데, 우리는 해당 없음)

**대안이 궁금하다면**: Fly.io나 Railway는 5분이면 배포되지만 월 $5 정도 듭니다.
해커톤 직전에 시간이 급하면 그쪽이 낫고, 계속 굴릴 거면 오라클이 낫습니다.

---

## 1. 오라클 클라우드 계정 만들기

https://www.oracle.com/kr/cloud/free/ → "무료로 시작하기"

**주의할 점 세 가지:**

1. **홈 리전은 나중에 못 바꿉니다.** 가입 중에 고르게 되는데,
   `한국 중부(서울)` 또는 `한국 북부(춘천)`을 고르면 지연시간이 짧습니다.
   다만 이 두 리전은 무료 ARM 서버 재고가 거의 항상 없습니다(아래 참고).
   재고를 우선한다면 `일본 동부(도쿄)`나 `싱가포르`도 괜찮습니다 — 봇 용도로는
   지연시간 차이를 체감하기 어렵습니다.

2. **신용/체크카드가 필요합니다.** 본인 확인용이고 Always Free 범위 안에서는
   과금되지 않습니다. 가입 시 1달러 정도가 임시 승인됐다가 취소됩니다.

3. **30일 무료 크레딧이 먼저 적용됩니다.** 30일이 지나면 계정이 자동으로
   "Always Free" 등급으로 내려가고, 그때 Always Free 범위를 넘는 리소스는
   정지됩니다. 아래에서 만들 서버는 Always Free 범위 안이라 계속 살아있습니다.

---

## 2. 서버(인스턴스) 만들기

콘솔 → 좌측 메뉴 ☰ → **컴퓨트(Compute)** → **인스턴스(Instances)** → **인스턴스 생성**

### 설정값

| 항목 | 값 |
|---|---|
| 이름 | `faq-bot` (아무거나) |
| 이미지 | **Canonical Ubuntu 22.04** 또는 24.04 (`Always Free Eligible` 라벨 확인) |
| Shape | 아래 참고 |
| 부트 볼륨 | 기본값 50GB 그대로 (Always Free 총 200GB 중 차감) |
| 네트워킹 | 기본값 그대로 (**공용 IPv4 주소 할당 = 예**) |
| SSH 키 | **"개인 키 저장"** 눌러서 `.key` 파일 다운로드 |

> 콘솔에서 이미지·Shape 옆에 붙는 **`Always Free Eligible`** 라벨을 꼭 확인하세요.
> 이 라벨이 없는 조합을 고르면 무료 범위를 벗어나 과금됩니다.

> ⚠️ **우분투 20.04를 고르면 안 됩니다.** 파이썬 3.8이라 이 프로젝트가
> 문법 오류로 실행되지 않습니다. 22.04 이상을 고르세요.

> ⚠️ **SSH 개인 키는 이때 딱 한 번만 받을 수 있습니다.** 못 받으면
> 서버에 접속할 방법이 없어서 인스턴스를 다시 만들어야 합니다.

### Shape 고르기 — AMD를 권합니다

무료로 고를 수 있는 선택지가 둘입니다.

**VM.Standard.E2.1.Micro (AMD)** ← 이걸 추천합니다
- 1/8 OCPU, 1GB RAM
- 성능은 낮지만 **거의 항상 생성됩니다**
- 이 봇은 메모리를 200MB도 안 쓰므로 차고 넘칩니다

**VM.Standard.A1.Flex (ARM)**
- Always Free 한도는 **2 OCPU / 12GB RAM** (월 1,500 OCPU 시간)
- 훨씬 좋지만 **"Out of host capacity" 오류로 생성이 계속 실패합니다.**
  몇 시간~며칠씩 재시도해야 잡히는 경우가 흔합니다
- ⚠️ **춘천(South Korea North)을 홈 리전으로 고르면 ARM 인스턴스를 아예 못 만듭니다.**
  오라클이 해당 리전에서 A1 생성을 지원하지 않습니다

봇 하나 돌리는 데 12GB RAM은 아무 의미가 없습니다. **AMD Micro로 시작하세요.**
나중에 무거운 걸 붙이고 싶어지면 그때 ARM에 도전해도 늦지 않습니다.

> **참고**: AMD Micro는 계정당 **2대**까지 만들 수 있지만, **가용성 도메인 한 곳에서만**
> 생성됩니다. AD를 바꿔가며 시도해도 소용없다는 뜻입니다(ARM과 다른 점).
> 또 Always Free 인스턴스는 반드시 **홈 리전**에 만들어야 합니다.

### "Out of capacity" 가 뜬다면

ARM을 고집할 경우에만 해당됩니다. 대응 방법:
- 가용성 도메인(AD-1, AD-2, AD-3)을 바꿔가며 시도
- 시간대를 바꿔 재시도 (한국 새벽 시간대가 상대적으로 잘 잡힙니다)
- 그냥 AMD Micro로 가기 ← 현실적인 답

---

## 3. 서버에 접속하기

인스턴스 상세 페이지에서 **공용 IP 주소**를 복사해 둡니다. (예: `152.70.xxx.xxx`)

### 윈도우 (PowerShell)

```powershell
# 1) 받은 키 파일을 안전한 곳으로 옮기고 권한을 잠근다
#    (권한이 열려 있으면 ssh가 "UNPROTECTED PRIVATE KEY FILE" 오류로 거부한다)
mkdir -Force $HOME\.ssh
move $HOME\Downloads\ssh-key-*.key $HOME\.ssh\oracle.key

icacls $HOME\.ssh\oracle.key /inheritance:r
icacls $HOME\.ssh\oracle.key /grant:r "$($env:USERNAME):(R)"

# 2) 접속 (IP는 본인 것으로)
ssh -i $HOME\.ssh\oracle.key ubuntu@152.70.xxx.xxx
```

처음 접속하면 `Are you sure you want to continue connecting?` 이 뜹니다 → `yes`

> 접속이 안 되고 멈춰 있다면 인스턴스가 아직 켜지는 중일 수 있습니다.
> 1~2분 기다린 뒤 다시 시도하세요.

---

## 4. 봇 설치 (여기부터는 명령 3줄)

서버에 접속한 상태에서:

```bash
git clone https://github.com/tlstkdgus/hackathon-faq-bot.git
cd hackathon-faq-bot
bash deploy/setup.sh
```

`setup.sh`가 알아서 해주는 일:

1. 파이썬·git 설치 및 버전 확인 (3.10 미만이면 친절하게 중단)
2. 서버 시간대를 한국시간으로 (로그 볼 때 헷갈리지 않게)
3. 스왑 메모리 2GB 생성 (RAM 1GB 인스턴스에서 메모리 부족 방지)
4. 가상환경 만들고 의존성 설치
5. `.env` 파일 준비
6. systemd 서비스 등록 (죽으면 자동 재시작 + 재부팅 시 자동 시작)

여러 번 실행해도 안전합니다.

---

## 5. 토큰 넣기

```bash
nano .env
```

`DISCORD_TOKEN=` 뒤에 디스코드 봇 토큰을 붙여넣습니다.
(Claude 답변도 쓰려면 `ANTHROPIC_API_KEY=` 도 채웁니다)

- 붙여넣기는 마우스 **오른쪽 클릭**
- 저장: `Ctrl+O` → `Enter` → `Ctrl+X`

그리고 시작:

```bash
sudo systemctl start faq-bot
journalctl -u faq-bot -f
```

로그에 이렇게 나오면 성공입니다:

```
   /슬래시 커맨드 4개 동기화 완료
✅ 로그인 성공: 해커톤FAQ봇#1234 (FAQ 49개 로드, 답변 모드: 키워드 + claude 폴백)
   질문 운영시간: 매일 10:00 ~ 17:00 (KST)
```

`Ctrl+C`로 로그 보기에서 빠져나옵니다. (봇은 계속 돌아갑니다)

이제 SSH 창을 닫아도, 내 컴퓨터를 꺼도 봇은 계속 동작합니다.

---

## 6. 평소 운영 명령어

```bash
# 상태 확인
systemctl status faq-bot

# 로그 실시간 보기 (Ctrl+C로 나가기)
journalctl -u faq-bot -f

# 최근 로그 100줄
journalctl -u faq-bot -n 100

# 재시작 / 중지 / 시작
sudo systemctl restart faq-bot
sudo systemctl stop faq-bot
sudo systemctl start faq-bot

# 코드 업데이트 (git pull + 의존성 갱신 + 재시작)
cd ~/hackathon-faq-bot && bash deploy/update.sh
```

### FAQ 내용만 고치고 싶을 때

서버에서 `faq.md`를 직접 고치고, 디스코드에서 `!리로드` 명령을 치면
봇을 재시작하지 않고 반영됩니다.

```bash
nano ~/hackathon-faq-bot/faq.md
# 저장 후 디스코드에서: !리로드
```

노션에서 관리하다가 옮기는 경우엔 로컬에서 고쳐 커밋하고 서버에서
`bash deploy/update.sh` 를 돌리는 쪽이 실수가 적습니다.

### 못 답한 질문 확인하기

```bash
tail -50 ~/hackathon-faq-bot/unanswered.log
```

자주 나오는 표현을 `faq.md`의 키워드에 추가하면 Claude 호출 없이
바로 답하게 되어 응답도 빨라지고 비용도 줍니다.

---

## 문제 해결

### 봇이 안 켜져요

```bash
journalctl -u faq-bot -n 50 --no-pager
```

로그에 나오는 메시지별 원인:

| 로그 메시지 | 원인과 해결 |
|---|---|
| `DISCORD_TOKEN 환경변수가 없습니다` | `.env`에 토큰을 안 넣었거나 `DISCORD_TOKEN=` 뒤가 비어 있음 |
| `❌ 디스코드 로그인 실패` | 토큰이 틀림. 개발자 포털에서 Reset Token으로 재발급 |
| `❌ MESSAGE CONTENT INTENT가 꺼져 있습니다` | 개발자 포털 → Bot → Privileged Gateway Intents에서 켜기 |
| `⚠️ FAQ 항목이 0개입니다` | `faq.md` 형식 문제. `## 주제 \| 키워드1, 키워드2` 형태인지 확인 |
| `파이썬 3.10 이상이 필요합니다` | 우분투 20.04를 고른 것. 22.04로 인스턴스를 다시 만드세요 |

### 슬래시 커맨드(`/해커톤질문`)가 디스코드에 안 보여요

`.env`의 `DISCORD_GUILD_ID`가 비어 있으면 전역 등록이라 디스코드 반영에
**최대 1시간**이 걸립니다. 서버 ID를 넣으면 즉시 반영됩니다.

```
DISCORD_GUILD_ID=1234567890123456789
```

서버 ID 확인: 디스코드 설정 → 고급 → 개발자 모드 ON →
서버 아이콘 우클릭 → "서버 ID 복사"

넣은 뒤 `sudo systemctl restart faq-bot`.

### 답변이 느려요

키워드로 못 잡은 질문만 Claude API를 부르는데, 여기서 몇 초가 걸립니다.
자주 나오는 질문은 `unanswered.log`를 보고 `faq.md` 키워드에 추가하세요.
키워드로 잡히면 즉시(0초) 답합니다.

### 서버가 갑자기 사라졌어요 ⚠️ (이 봇에 실제로 해당됩니다)

오라클은 **유휴 상태인 Always Free 인스턴스를 회수**합니다. 판단 기준은
7일 동안 아래를 **모두** 만족하는 경우입니다:

- CPU 사용률 95번째 백분위수가 20% 미만
- 네트워크 사용률 20% 미만
- (ARM A1만 해당) 메모리 사용률 20% 미만

**FAQ 봇은 이 조건에 정확히 걸립니다.** 평소 CPU를 거의 안 쓰고 트래픽도
미미하니까요. "봇이 켜져 있으니 괜찮겠지"는 틀린 생각입니다.

**대응 방법**: 오라클 콘솔에서 계정을 **종량제(Pay As You Go)로 업그레이드**하세요.
오라클 문서에 따르면 업그레이드 후에도 Always Free 범위 안의 리소스에는 요금을
청구하지 않고, 한도를 넘는 사용분만 과금됩니다. 유휴 회수 정책은 Always Free
계정을 대상으로 하므로, 업그레이드가 가장 널리 쓰이는 회피책입니다.

카드가 등록되므로 실수로 한도를 넘기는 게 걱정된다면 **구획 할당량
(Compartment Quotas)** 을 걸어 리소스 생성 자체를 제한할 수 있습니다.

업그레이드가 부담스럽다면, 해커톤처럼 **기간이 정해진 행사**에서는 어차피
며칠만 쓰고 끝나므로 그냥 두셔도 됩니다. 회수는 7일 유휴가 조건이니까요.

### 오라클 콘솔에서 인스턴스가 "Stopped" 상태예요

콘솔에서 **시작(Start)** 을 누르면 됩니다. systemd에 등록해 뒀으므로
서버가 켜지면 봇도 자동으로 다시 뜹니다.

---

## 보안 체크리스트

- [ ] `.env` 파일은 절대 git에 커밋하지 않는다 (`.gitignore`에 등록돼 있음)
- [ ] `unanswered.log`, `stats.log`도 커밋하지 않는다 (학생 질문·ID 포함)
- [ ] SSH 개인 키(`.key`)를 다른 사람과 공유하지 않는다
- [ ] 토큰이 유출된 것 같으면 즉시 개발자 포털에서 Reset Token
- [ ] 해커톤이 끝나면 봇 토큰과 API 키를 폐기한다
