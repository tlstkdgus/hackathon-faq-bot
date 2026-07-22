# -*- coding: utf-8 -*-
"""
해커톤 FAQ 디스코드 봇
- faq.md에 있는 키워드/답변으로 학생 질문에 자동 응답
- 사용법: 봇을 멘션(@봇이름)하고 질문하거나, !질문 <내용>
- !주제 : 답변 가능한 주제 목록
- !리로드 : faq.md 수정 후 다시 불러오기 (관리자용)
"""

import os
import datetime

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from faq_engine import load_faq, find_answer, topic_list
import llm  # LLM 백엔드 스위치 (claude / openai …) — LLM_PROVIDER 환경변수로 선택

load_dotenv()  # .env 파일이 있으면 여기서 읽어와 환경변수로 등록 (README 참고)
TOKEN = os.environ.get("DISCORD_TOKEN")  # 환경변수로 토큰 관리 (README 참고)
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # 설정하면 /질문 슬래시 커맨드가 즉시 반영(선택)
FAQ_FILE = "faq.md"
MISS_LOG_FILE = "unanswered.log"  # 키워드로 못 잡은 질문 기록 (운영진 FAQ 보강용)

intents = discord.Intents.default()
intents.message_content = True  # 개발자 포털에서 MESSAGE CONTENT INTENT 켜야 함

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
faq_entries = load_faq(FAQ_FILE)

NO_MATCH_MSG = (
    "음… 그 질문에 맞는 답을 못 찾았어요. 😅\n"
    "`!주제` 를 입력하면 제가 답할 수 있는 주제 목록을 볼 수 있어요.\n"
    "그래도 해결이 안 되면 운영진에게 직접 문의해 주세요!"
)


def log_miss(question: str, handled_by: str) -> None:
    """키워드로 못 잡은 질문을 로그 파일에 남긴다.

    handled_by: 'claude'(Claude가 대신 답함) 또는 'nomatch'(아무도 못 답함).
    운영진은 이 로그를 보고 자주 나오는 표현을 faq.md 키워드에 추가하면 된다.
    """
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}\t[{handled_by}]\t{question}\n"
    try:
        with open(MISS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"⚠️ 로그 기록 실패: {e}")


def build_reply(question: str) -> str:
    """응답 생성의 단일 진입점.

    1) 먼저 강화된 키워드 매칭으로 답을 찾는다 (빠르고 무료).
    2) 키워드로 확실히 못 찾은 경우에만 Claude Haiku로 자연어 답변 시도
       (ANTHROPIC_API_KEY가 있을 때). → 대부분은 무료, 애매한 질문만 API 사용.
    3) Claude도 못 쓰거나 오류면 안내 메시지.
    키워드가 못 잡은 질문은 모두 로그에 남겨 운영진이 FAQ를 보강할 수 있게 한다.
    """
    entry = find_answer(question, faq_entries)
    if entry is not None:
        return f"**📌 {entry.title}**\n{entry.answer}"

    # 키워드로 못 찾음 → LLM에게 넘김 (자연어로 이해 시도)
    handled_by = "nomatch"
    reply = NO_MATCH_MSG
    if llm.is_enabled():
        try:
            answer = llm.answer(question, faq_entries)
            if answer:
                reply, handled_by = answer, llm.PROVIDER
        except Exception as e:
            print(f"⚠️ LLM({llm.PROVIDER}) 오류: {e}")

    log_miss(question, handled_by)
    return reply


@bot.event
async def on_ready():
    mode = f"키워드 + {llm.PROVIDER} 폴백" if llm.is_enabled() else "키워드 전용"
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


NUDGE_MSG = "🔒 질문은 **`/해커톤질문`** 으로 해주세요! 그래야 질문과 답변이 **나에게만** 보여요."

USAGE_MSG = (
    "**질문하는 방법** 🦁\n"
    "🔒 **`/해커톤질문 <내용>`** — 질문·답변이 **나에게만** 보여요 (남들에게 안 보임)\n"
    "· **`/해커톤주제`** — 제가 답할 수 있는 주제 목록 (나에게만 보임)\n"
    "· **`/해커톤도움`** — 이 사용법 안내"
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
    # Claude 폴백이 몇 초 걸릴 수 있으니 먼저 응답 지연 예약(3초 제한 회피), 둘 다 비공개.
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(build_reply(내용), ephemeral=True)


@bot.tree.command(name="해커톤주제", description="제가 답할 수 있는 주제 목록을 나에게만 보여줘요")
async def slash_topics(interaction: discord.Interaction):
    """/해커톤주제 — 답변 가능한 주제 목록 (본인에게만 보임)."""
    await interaction.response.send_message(
        f"**제가 답할 수 있는 주제예요!**\n{topic_list(faq_entries)}", ephemeral=True
    )


@bot.tree.command(name="해커톤도움", description="사용법 안내를 나에게만 보여줘요")
async def slash_help(interaction: discord.Interaction):
    """/해커톤도움 — 사용법 안내 (본인에게만 보임)."""
    await interaction.response.send_message(USAGE_MSG, ephemeral=True)


@bot.command(name="리로드")
@commands.has_permissions(manage_guild=True)
async def reload_faq(ctx: commands.Context):
    """!리로드 — faq.md를 다시 불러오기 (서버 관리 권한 필요)"""
    global faq_entries
    faq_entries = load_faq(FAQ_FILE)
    await ctx.reply(f"🔄 FAQ를 다시 불러왔어요! (총 {len(faq_entries)}개 주제)")


@bot.event
async def on_command_error(ctx: commands.Context, error):
    """공개 `!명령`으로 질문해도 답하지 않고 /질문 사용을 안내한다."""
    if isinstance(error, commands.MissingPermissions):
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
            "DISCORD_TOKEN 환경변수가 없습니다. README.md의 '토큰 설정' 부분을 참고하세요."
        )
    bot.run(TOKEN)
