# -*- coding: utf-8 -*-
"""
해커톤 FAQ 디스코드 봇
- faq.md에 있는 키워드/답변으로 학생 질문에 자동 응답
- 키워드로 못 잡으면 LLM(OpenAI/Claude)이 FAQ 자료를 근거로 자연어 답변 (선택)
- 질문/답변은 항상 비공개(ephemeral)로 나가고, 공개 채팅에는 안내만 남긴다

명령어
- /해커톤질문 <내용> : 질문 (나에게만 보임)
- /해커톤주제        : 답변 가능한 주제 목록
- /해커톤도움        : 사용법
- /해커톤통계        : 사용 통계 (서버 관리자 전용)
- !리로드            : faq.md 수정 후 다시 불러오기 (서버 관리자 전용)

실행: python bot.py  (서버 배포는 deploy/DEPLOY.md 참고)
"""

import os
import sys
import asyncio

# 이 프로젝트는 파이썬 3.10 이상이 필요하다.
# (hours.py의 `datetime | None` 타입 표기가 3.9에서는 문법 오류로 죽는다.)
# 서버에서 우분투 20.04 같은 구버전을 골랐을 때 원인 모를 SyntaxError로
# 헤매지 않도록, 여기서 먼저 사람이 읽을 수 있는 메시지로 알려준다.
if sys.version_info < (3, 10):
    raise SystemExit(
        f"파이썬 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]}).\n"
        "우분투라면: sudo apt install python3.10  또는 우분투 22.04 이상을 쓰세요."
    )

import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

# .env 로드는 반드시 아래의 로컬 모듈 import보다 먼저 실행해야 한다.
# hours.py, llm.py는 import되는 순간(모듈 최상단)에 os.environ에서 설정값을
# 읽어 상수로 고정하므로, load_dotenv()가 늦게 실행되면 .env 값이 무시되고
# 코드에 적힌 기본값만 계속 쓰이게 된다 (예: QA_END_HOUR가 항상 17로 고정되던 버그).
load_dotenv()  # .env 파일이 있으면 여기서 읽어와 환경변수로 등록 (README 참고)

from faq_engine import load_faq, find_answer, topic_list
import llm  # LLM 백엔드 스위치 (claude / openai …) — LLM_PROVIDER 환경변수로 선택
from stats_engine import log_miss, log_usage, compute_stats
import hours  # 질문 운영시간 판단 (QA_START_HOUR ~ QA_END_HOUR)
import digest  # 미답변 질문 분석 → 운영진용 일일 리포트
from paths import FAQ_FILE, DATA_DIR  # 절대경로. 서버(systemd)에서 실행해도 안전하다

TOKEN = os.environ.get("DISCORD_TOKEN")  # 환경변수로 토큰 관리 (README 참고)
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 설정하면 /질문 슬래시 커맨드가 즉시 반영(선택)

# ── 일일 미답변 리포트 ──
# 매일 정해진 시각에 '키워드로 못 잡은 질문' 요약을 지정 채널로 보낸다.
# ⚠️ 리포트에는 학생 질문 원문이 담기므로 반드시 운영진만 보는 채널을 지정할 것.
DIGEST_CHANNEL_ID = os.environ.get("DIGEST_CHANNEL_ID", "").strip()
try:
    DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "9"))
except ValueError:
    DIGEST_HOUR = 9
    print("⚠️ DIGEST_HOUR 값이 숫자가 아닙니다. 기본값 9시를 사용합니다.")

# 디스코드 메시지 한 건의 최대 길이. 넘기면 전송 자체가 실패(HTTP 400)하므로
# 보내기 직전에 잘라준다. faq.md에 운영진이 아주 긴 답변을 넣어도 봇이 죽지 않게 하는 안전장치.
DISCORD_MAX_LEN = 2000


def _parse_channel_ids(raw: str, name: str = "ALLOWED_CHANNEL_IDS") -> set:
    """"123,456" 같은 문자열을 채널 ID 집합으로. 숫자가 아닌 값은 경고 후 버린다.

    조용히 버리면 오타 하나로 질문 채널이 통째로 막히는데, 봇은 멀쩡히 떠 있어서
    원인을 찾기 어렵다. 시작 로그에 남겨 바로 알아채게 한다.
    name은 경고에 찍을 환경변수 이름이다 (어느 값이 틀렸는지 알려주려고).
    """
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            print(f"⚠️ {name}에 숫자가 아닌 값이 있어 무시합니다: {part!r}")
            continue
        ids.add(int(part))
    return ids


# ── 질문 채널 제한 ──
# 학생용 명령(/해커톤질문·/해커톤주제·/해커톤도움)을 받을 채널을 제한한다.
# 비워두면 제한 없음 = 봇이 볼 수 있는 모든 채널에서 동작 (기존 동작 그대로).
# 쉼표로 여러 개 지정 가능. 운영진 명령(/해커톤통계·!리로드)에는 적용하지 않는다.
ALLOWED_CHANNEL_IDS = _parse_channel_ids(os.environ.get("ALLOWED_CHANNEL_IDS", ""))

# ── 운영진 명령 채널 제한 ──
# /해커톤통계·!리로드를 받을 채널. 별도 환경변수를 두지 않고 DIGEST_CHANNEL_ID를
# 재사용한다 — 미답변 리포트가 가는 곳이 곧 운영진 전용 채널이라, 운영진 명령을
# 쓸 곳도 같은 채널이 자연스럽다. 설정이 하나 줄어드는 이점도 있다.
#
# 주의: 리포트 채널을 옮기면 운영진 명령을 쓸 수 있는 곳도 같이 따라간다.
# 둘을 따로 두고 싶어지면 ADMIN_CHANNEL_IDS를 새로 만들 것.
# 비어 있으면(리포트 기능을 안 쓰면) 제한 없음 = 기존 동작 그대로.
ADMIN_CHANNEL_IDS = _parse_channel_ids(DIGEST_CHANNEL_ID, "DIGEST_CHANNEL_ID")


def _channel_ok(channel_id, allowed: set) -> bool:
    """channel_id가 허용 목록에 있는지. 목록이 비어 있으면 제한 없음.

    학생용·운영진용 게이트가 이 함수 하나를 공유한다. 검사를 두 벌로 나눠두면
    한쪽만 고쳤을 때 동작이 조용히 갈라진다.
    """
    if not allowed:
        return True
    return channel_id in allowed


def is_allowed_channel(interaction: "discord.Interaction") -> bool:
    """이 채널에서 학생용 명령을 받아도 되는지.

    제한이 설정돼 있지 않으면 항상 True다. 제한이 걸려 있으면 DM도 막힌다
    (DM의 channel_id는 목록에 있을 수 없으므로).
    """
    return _channel_ok(interaction.channel_id, ALLOWED_CHANNEL_IDS)


def is_admin_channel(channel_id) -> bool:
    """이 채널에서 운영진 명령(/해커톤통계·!리로드)을 받아도 되는지.

    슬래시 커맨드는 interaction.channel_id, `!리로드`는 ctx.channel.id를
    넘긴다. 타입이 달라서 인터랙션 객체가 아니라 ID를 받는다.
    """
    return _channel_ok(channel_id, ADMIN_CHANNEL_IDS)


def _channel_links(allowed: set) -> str:
    """`<#ID>` 링크 목록. 디스코드가 클릭 가능한 채널 링크로 렌더링한다.

    채널 이름을 문자열로 박아두면 채널명이 바뀌었을 때 조용히 틀린 안내가
    나가지만, ID 링크는 이름이 바뀌어도 항상 맞는 곳을 가리킨다.
    """
    return " ".join(f"<#{cid}>" for cid in sorted(allowed))


def wrong_channel_msg() -> str:
    """학생용 명령을 허용 채널 밖에서 썼을 때의 안내. 갈 곳을 알려주는 게 핵심."""
    return f"🔒 여기서는 질문을 받지 않아요.\n{_channel_links(ALLOWED_CHANNEL_IDS)} 에서 물어봐 주세요!"


def wrong_admin_channel_msg() -> str:
    """운영진 명령을 허용 채널 밖에서 썼을 때의 안내."""
    return (
        f"🔒 운영진 명령은 여기서 쓸 수 없어요.\n"
        f"{_channel_links(ADMIN_CHANNEL_IDS)} 에서 사용해 주세요!"
    )

intents = discord.Intents.default()
intents.message_content = True  # 개발자 포털에서 MESSAGE CONTENT INTENT 켜야 함

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def _load_entries() -> list:
    """faq.md를 읽어온다. 파일이 없거나 비어 있으면 눈에 띄게 경고한다.

    예전에는 상대경로를 써서, 실행 위치가 다르면 파일을 못 찾고 조용히
    0개가 로드된 채로 봇이 떴다. 이제는 경로도 절대경로고, 문제가 있으면
    로그에 크게 남긴다.
    """
    try:
        entries = load_faq(str(FAQ_FILE))
    except FileNotFoundError:
        print(f"❌ FAQ 파일을 찾을 수 없습니다: {FAQ_FILE}")
        return []
    if not entries:
        print(f"⚠️ FAQ 항목이 0개입니다. {FAQ_FILE} 형식을 확인하세요 (## 주제 | 키워드).")
    return entries


faq_entries = _load_entries()

NO_MATCH_MSG = (
    "음… 그 질문에 맞는 답을 못 찾았어요. 😅\n"
    "`/해커톤주제` 를 입력하면 제가 답할 수 있는 주제 목록을 볼 수 있어요.\n"
    "그래도 해결이 안 되면 운영진에게 직접 문의해 주세요!"
)


def clip(text: str, limit: int = DISCORD_MAX_LEN) -> str:
    """디스코드 길이 제한에 맞게 자른다 (넘칠 때만 동작)."""
    if len(text) <= limit:
        return text
    tail = "\n…(내용이 길어 줄였어요. 자세한 건 운영진에게 문의해 주세요!)"
    return text[: limit - len(tail)] + tail


def build_reply(question: str, user_id: int) -> str:
    """응답 생성의 단일 진입점.

    1) 먼저 강화된 키워드 매칭으로 답을 찾는다 (빠르고 무료).
    2) 키워드로 확실히 못 찾은 경우에만 LLM으로 자연어 답변 시도 (API 키가 있을 때).
       → 대부분은 무료, 애매한 질문만 API 사용.
    3) LLM도 못 쓰거나 모든 백엔드가 실패하면 안내 메시지.
    키워드가 못 잡은 질문은 unanswered.log에, 모든 질문은 stats.log(통계용)에 남긴다.
    """
    entry = find_answer(question, faq_entries)
    if entry is not None:
        log_usage(user_id, f"hit:{entry.title}", question)
        # 지난 일정을 안내하는 항목이면 경고를 맨 위에 붙인다.
        # 운영진이 faq.md를 고칠 때까지 학생이 끝난 안내를 그대로 받는 걸 막는다.
        # (날짜 비교뿐이라 LLM이 끼어들지 않는다 — digest.stale_notice 참고)
        return clip(f"**📌 {entry.title}**\n{digest.stale_notice(entry.title)}{entry.answer}")

    # 키워드로 못 찾음 → LLM에게 넘김 (자연어로 이해 시도)
    handled_by = "nomatch"
    reply = NO_MATCH_MSG
    if llm.is_enabled():
        try:
            answer = llm.answer(question, faq_entries)
            if answer:
                # llm.last_used = 실제로 답을 만든 백엔드 이름.
                # 폴백이 동작했을 수 있으므로 PROVIDER(설정값)가 아니라 이걸 기록한다.
                reply, handled_by = answer, llm.last_used
        except Exception as e:
            print(f"⚠️ LLM 답변 실패(모든 백엔드): {e}")

    log_miss(question, handled_by, user_id)
    log_usage(user_id, handled_by, question)
    return clip(reply)


@bot.event
async def on_ready():
    mode = f"키워드 + {llm.describe()}" if llm.is_enabled() else "키워드 전용"
    # 슬래시 커맨드(/질문) 동기화. GUILD_ID가 있으면 해당 서버에 즉시 반영,
    # 없으면 전역 동기화(디스코드 반영에 최대 1시간 걸릴 수 있음).
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        print(f"   /슬래시 커맨드 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"⚠️ 슬래시 커맨드 동기화 실패: {e}")
    print(f"✅ 로그인 성공: {bot.user} (FAQ {len(faq_entries)}개 로드, 답변 모드: {mode})")
    print(f"   질문 운영시간: 매일 {hours.describe()} (KST)")
    if ALLOWED_CHANNEL_IDS:
        print(f"   질문 채널: {len(ALLOWED_CHANNEL_IDS)}개로 제한 "
              f"({', '.join(str(c) for c in sorted(ALLOWED_CHANNEL_IDS))})")
    else:
        print("   질문 채널: 제한 없음 (모든 채널)")
    if ADMIN_CHANNEL_IDS:
        print(f"   운영진 채널: {', '.join(str(c) for c in sorted(ADMIN_CHANNEL_IDS))} "
              f"(/해커톤통계·!리로드)")
    else:
        print("   운영진 채널: 제한 없음 (DIGEST_CHANNEL_ID 미설정)")
    print(f"   FAQ 파일: {FAQ_FILE}")
    print(f"   로그 폴더: {DATA_DIR}")
    if not faq_entries:
        print("❗ FAQ가 0개라 지금은 어떤 질문에도 답할 수 없습니다. faq.md를 확인하세요.")

    # on_ready는 재접속 때마다 다시 호출된다. 그때 루프를 또 시작하면
    # 리포트가 하루에 여러 번 나가므로 실행 중인지 먼저 확인한다.
    if DIGEST_CHANNEL_ID and not daily_digest.is_running():
        daily_digest.start()
        print(f"   미답변 리포트: 매일 {DIGEST_HOUR}:00 (KST) → 채널 {DIGEST_CHANNEL_ID}")
    elif not DIGEST_CHANNEL_ID:
        print("   미답변 리포트: 꺼짐 (DIGEST_CHANNEL_ID 미설정)")


@tasks.loop(time=datetime.time(hour=DIGEST_HOUR, minute=0, tzinfo=hours.KST))
async def daily_digest():
    """매일 정해진 시각에 '키워드로 못 잡은 질문' 요약을 운영진 채널로 보낸다.

    ⚠️ 리포트에는 학생 질문 원문이 들어간다. DIGEST_CHANNEL_ID에는
    반드시 운영진만 볼 수 있는 채널을 지정할 것.

    전송에 성공했을 때만 '마지막 실행 시각'을 저장한다. 그래야 채널을 잘못
    지정했거나 권한이 없어 실패했을 때, 다음 날 그 기간까지 함께 보고된다.
    """
    try:
        channel = bot.get_channel(int(DIGEST_CHANNEL_ID))
        if channel is None:
            # 캐시에 없으면 API로 직접 조회 (봇 재시작 직후 등)
            channel = await bot.fetch_channel(int(DIGEST_CHANNEL_ID))
    except Exception as e:
        print(f"⚠️ 리포트 채널({DIGEST_CHANNEL_ID})을 찾을 수 없습니다: {e}")
        return

    try:
        report, _ = await asyncio.to_thread(digest.make_digest, faq_entries)
        await channel.send(clip(report))
        await asyncio.to_thread(digest.save_last_run)
    except Exception as e:
        print(f"⚠️ 미답변 리포트 전송 실패: {e}")


@daily_digest.before_loop
async def _before_digest():
    """봇이 디스코드에 완전히 연결된 뒤에 루프를 돌린다."""
    await bot.wait_until_ready()


NUDGE_MSG = "🔒 질문은 **`/해커톤질문`** 으로 해주세요! 그래야 질문과 답변이 **나에게만** 보여요."

CLOSED_MSG = (
    f"🌙 지금은 질문 운영시간이 아니에요.\n"
    f"매일 **{hours.describe()}** 에만 답변드리고 있어요. "
    "운영시간에 다시 물어봐 주세요!"
)

USAGE_MSG = (
    "**질문하는 방법** 🦁\n"
    "🔒 **`/해커톤질문 <내용>`** — 질문·답변이 **나에게만** 보여요 (남들에게 안 보임)\n"
    f"   (운영시간: 매일 {hours.describe()})\n"
    "· **`/해커톤주제`** — 제가 답할 수 있는 주제 목록, 카테고리별로 정리해서 보여드려요 (나에게만 보임)\n"
    "· **`/해커톤도움`** — 이 사용법 안내\n"
    "· **`/해커톤통계`** — (운영진 전용) 사용 통계"
)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    # 멘션으로 물어봐도 공개로 답하지 않고 /질문 사용을 안내 (답변은 항상 비공개)
    if bot.user in message.mentions:
        await message.reply(NUDGE_MSG)
        return
    await bot.process_commands(message)  # !리로드(관리자) 등 명령어 처리


@bot.tree.command(name="해커톤질문", description="해커톤 FAQ에 대해 물어보면 '나에게만' 보이게 답해드려요")
@app_commands.describe(내용="궁금한 내용을 적어주세요")
async def slash_ask(interaction: discord.Interaction, 내용: str):
    """/해커톤질문 <내용> — 질문과 답변 모두 질문한 본인에게만 보임(ephemeral)."""
    # 허용 채널이 아니면 갈 곳을 안내한다. ephemeral이라 채널엔 안 남는다.
    # (응답을 아예 안 하면 디스코드가 "응답하지 않았습니다" 오류를 띄워
    #  학생 눈에는 봇 고장으로 보인다. 그래서 안내를 보내는 쪽을 택했다.)
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(wrong_channel_msg(), ephemeral=True)
        return
    if not hours.is_operating_hours():
        await interaction.response.send_message(CLOSED_MSG, ephemeral=True)
        return
    # LLM 폴백이 몇 초 걸릴 수 있으니 먼저 응답 지연 예약(3초 제한 회피), 둘 다 비공개.
    await interaction.response.defer(ephemeral=True)
    # build_reply 내부의 LLM 호출(anthropic/openai SDK)이 동기(blocking) 함수라
    # 그대로 부르면 응답을 기다리는 동안 봇 전체(다른 학생들 요청 포함)가 멈춘다.
    # 별도 스레드에서 돌려서 이벤트 루프가 다른 사람 요청을 계속 처리하게 한다.
    #
    # defer()를 이미 불렀기 때문에, 여기서 예외가 나면 학생 화면에는
    # "애플리케이션이 응답하지 않습니다"만 남고 아무 안내도 못 받는다.
    # 그래서 무슨 일이 생기든 반드시 followup을 하나는 보내도록 감싼다.
    try:
        reply = await asyncio.to_thread(build_reply, 내용, interaction.user.id)
    except Exception as e:
        print(f"⚠️ 답변 생성 중 오류: {e}")
        reply = "앗, 답변을 만드는 중에 문제가 생겼어요. 😢 잠시 후 다시 시도해 주세요."
    await interaction.followup.send(reply, ephemeral=True)


@bot.tree.command(name="해커톤주제", description="제가 답할 수 있는 주제 목록을 나에게만 보여줘요")
async def slash_topics(interaction: discord.Interaction):
    """/해커톤주제 — 답변 가능한 주제 목록 (본인에게만 보임)."""
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(wrong_channel_msg(), ephemeral=True)
        return
    if not faq_entries:
        await interaction.response.send_message(
            "아직 등록된 주제가 없어요. 운영진에게 알려주세요!", ephemeral=True
        )
        return
    # 주제가 많아지면 2000자를 넘길 수 있으므로 잘라서 보낸다.
    await interaction.response.send_message(
        clip(f"**제가 답할 수 있는 주제예요!**\n{topic_list(faq_entries)}"), ephemeral=True
    )


@bot.tree.command(name="해커톤도움", description="사용법 안내를 나에게만 보여줘요")
async def slash_help(interaction: discord.Interaction):
    """/해커톤도움 — 사용법 안내 (본인에게만 보임)."""
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(wrong_channel_msg(), ephemeral=True)
        return
    await interaction.response.send_message(USAGE_MSG, ephemeral=True)


@bot.tree.command(name="해커톤통계", description="[관리자] 지금까지 질문 사용 통계를 보여줘요")
async def slash_stats(interaction: discord.Interaction):
    """/해커톤통계 — 서버 관리 권한이 있는 사람만, 운영진 채널에서만."""
    # 권한을 먼저 본다. 권한 없는 사람에게 운영진 채널 링크를 알려줄 이유가 없다.
    perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
    if not (perms and perms.manage_guild):
        await interaction.response.send_message("이 명령은 서버 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    if not is_admin_channel(interaction.channel_id):
        await interaction.response.send_message(wrong_admin_channel_msg(), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    summary = await asyncio.to_thread(compute_stats)
    await interaction.followup.send(summary, ephemeral=True)


@bot.command(name="리로드")
@commands.has_permissions(manage_guild=True)
async def reload_faq(ctx: commands.Context):
    """!리로드 — faq.md를 다시 불러오기 (서버 관리 권한 + 운영진 채널)"""
    global faq_entries
    # 슬래시 커맨드와 달리 ctx라서 channel_id 대신 ctx.channel.id를 넘긴다.
    # 여기 응답은 ephemeral이 아니라 채널에 남는다. 그래서 학생 채널에서
    # 눌렸을 때 "리로드 완료" 같은 운영 메시지가 공개로 새지 않게 막는 의미도 있다.
    if not is_admin_channel(ctx.channel.id):
        await ctx.reply(wrong_admin_channel_msg())
        return
    entries = _load_entries()
    if not entries:
        # 실수로 faq.md를 깨뜨렸을 때, 기존에 잘 돌던 FAQ까지 날려버리면 안 된다.
        # 새로 읽은 결과가 0개면 이전 내용을 그대로 유지하고 경고만 한다.
        await ctx.reply(
            f"⚠️ faq.md에서 주제를 하나도 못 읽었어요. 형식을 확인해 주세요.\n"
            f"(기존 {len(faq_entries)}개 주제는 그대로 유지했어요.)"
        )
        return
    faq_entries = entries
    await ctx.reply(f"🔄 FAQ를 다시 불러왔어요! (총 {len(faq_entries)}개 주제)")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    """공개 `!명령`으로 질문해도 답하지 않고 /질문 사용을 안내한다."""
    if isinstance(error, commands.MissingPermissions):
        # 권한 검사는 데코레이터라 명령 본문(=채널 검사)보다 먼저 돈다.
        # 그래서 권한 없는 학생이 학생 채널에서 `!리로드`를 치면 채널 게이트에
        # 닿기 전에 여기로 온다. 이 응답은 ephemeral이 아니라 채널에 남으므로,
        # 운영진 채널이 아니면 조용히 무시한다 (장난으로 반복하면 안내만 쌓인다).
        # 제한이 설정돼 있지 않으면 is_admin_channel()이 True라 기존 동작 그대로.
        if is_admin_channel(ctx.channel.id):
            await ctx.reply("이 명령은 서버 관리자만 사용할 수 있어요.")
        return
    if isinstance(error, commands.CommandNotFound):
        # !질문, !식사 등 → 공개로 답하지 않고 /질문 안내
        await ctx.reply(NUDGE_MSG)
        return
    print(f"⚠️ 명령 처리 오류: {error}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN 환경변수가 없습니다. README.md의 '토큰 설정' 부분을 참고하세요.\n"
            "(서버라면 /etc/faq-bot.env 또는 프로젝트 폴더의 .env 파일을 확인하세요.)"
        )
    try:
        # log_handler=None: discord.py가 자체 로그 설정을 하지 않게 두면
        # print 출력이 그대로 systemd 저널(journalctl)에 남아 보기 편하다.
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        raise SystemExit(
            "❌ 디스코드 로그인 실패: DISCORD_TOKEN이 잘못됐습니다.\n"
            "   디스코드 개발자 포털 → Bot → Reset Token 으로 새 토큰을 발급받아 넣으세요."
        )
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "❌ MESSAGE CONTENT INTENT가 꺼져 있습니다.\n"
            "   개발자 포털 → Bot → Privileged Gateway Intents →\n"
            "   'MESSAGE CONTENT INTENT'를 켜고 저장한 뒤 다시 실행하세요."
        )
