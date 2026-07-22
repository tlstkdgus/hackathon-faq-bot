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
from discord.ext import commands
from dotenv import load_dotenv

from faq_engine import load_faq, find_answer, topic_list
import llm  # LLM 백엔드 스위치 (claude / openai …) — LLM_PROVIDER 환경변수로 선택

load_dotenv()  # .env 파일이 있으면 여기서 읽어와 환경변수로 등록 (README 참고)
TOKEN = os.environ.get("DISCORD_TOKEN")  # 환경변수로 토큰 관리 (README 참고)
FAQ_FILE = "faq.md"
MISS_LOG_FILE = "unanswered.log"  # 키워드로 못 잡은 질문 기록 (운영진 FAQ 보강용)

intents = discord.Intents.default()
intents.message_content = True  # 개발자 포털에서 MESSAGE CONTENT INTENT 켜야 함

bot = commands.Bot(command_prefix="!", intents=intents)
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
    print(f"✅ 로그인 성공: {bot.user} (FAQ {len(faq_entries)}개 로드, 답변 모드: {mode})")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 봇을 멘션하면서 질문한 경우
    if bot.user in message.mentions:
        question = message.content
        for m in message.mentions:
            question = question.replace(m.mention, "")
        question = question.strip()
        if question:
            await message.reply(build_reply(question))
            return

    await bot.process_commands(message)  # !질문, !주제 등 명령어 처리


@bot.command(name="질문")
async def ask(ctx: commands.Context, *, question: str = ""):
    """!질문 <내용> — FAQ에서 답을 찾아 답변"""
    if not question.strip():
        await ctx.reply("`!질문 와이파이 비밀번호 뭐예요?` 처럼 질문을 함께 적어 주세요!")
        return
    await ctx.reply(build_reply(question))


@bot.command(name="주제")
async def topics(ctx: commands.Context):
    """!주제 — 답변 가능한 주제 목록"""
    await ctx.reply(f"**제가 답할 수 있는 주제예요!**\n{topic_list(faq_entries)}")


@bot.command(name="리로드")
@commands.has_permissions(manage_guild=True)
async def reload_faq(ctx: commands.Context):
    """!리로드 — faq.md를 다시 불러오기 (서버 관리 권한 필요)"""
    global faq_entries
    faq_entries = load_faq(FAQ_FILE)
    await ctx.reply(f"🔄 FAQ를 다시 불러왔어요! (총 {len(faq_entries)}개 주제)")


USAGE_MSG = (
    "**질문하는 방법** 🦁\n"
    "· 저를 **멘션**하고 물어보기 — 예: `@질문봇 와이파이 비번 뭐야`\n"
    "· `!질문 <내용>` — 예: `!질문 sjf 트랙 뭐야`\n"
    "· `!<키워드>` 로 바로 — 예: `!식사`, `!멘토링`, `!주차`, `!일정`\n"
    "· `!주제` — 제가 답할 수 있는 주제 목록 보기"
)


@bot.command(name="도움")
async def help_cmd(ctx: commands.Context):
    """!도움 — 사용법 안내"""
    await ctx.reply(USAGE_MSG)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    """등록 안 된 `!명령`은 질문으로 처리하고, 그 외 에러는 조용히 로깅."""
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("이 명령은 서버 관리자만 사용할 수 있어요.")
        return
    if isinstance(error, commands.CommandNotFound):
        # `!식사`, `!와이파이 비번` 처럼 친 경우 → 프리픽스만 떼고 질문으로 처리
        question = ctx.message.content.lstrip("!").strip()
        if question:
            await ctx.reply(build_reply(question))
        return
    print(f"⚠️ 명령 처리 오류: {error}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN 환경변수가 없습니다. README.md의 '토큰 설정' 부분을 참고하세요."
        )
    bot.run(TOKEN)
