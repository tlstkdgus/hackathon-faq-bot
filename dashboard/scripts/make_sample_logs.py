# -*- coding: utf-8 -*-
"""
make_sample_logs.py — 현황판 시연용 예시 로그를 만든다.

실제 로그(stats.log, unanswered.log)에는 학생 질문 원문과 디스코드 사용자 ID가
들어 있어 저장소에 올릴 수 없다. 그래서 공개 시연은 이 스크립트가 만든
예시 데이터로 한다.

무엇이 실제이고 무엇이 아닌가:
    - 실제: RETROSPECTIVE.md에 남긴 14기 운영 집계
            (날짜별 질문 수, 주제별 적중 수, 총 229건 / 키워드 185건 / LLM 44건 /
             미응답 0건 / 순 사용자 53명)
    - 아님: 질문 문장(주제명으로 만든 문장), 사용자 ID(무작위), 시각(무작위)
            단, LLM으로 넘어간 질문 문장은 회고 문서에 공개된 표현을 쓴다.

로그 형식은 봇과 똑같이 맞춘다 (CLAUDE.md '로그 형식' 참고).
    stats.log      : 시각 \t 사용자ID \t 결과 \t 질문
    unanswered.log : 시각 \t [처리주체] \t 사용자ID \t 질문

사용법:
    python dashboard/scripts/make_sample_logs.py            # dashboard/sample-data/에 생성
    python dashboard/scripts/make_sample_logs.py /tmp/data  # 원하는 폴더에 생성
"""

import datetime
import random
import sys
from pathlib import Path

SEED = 14  # 14기. 같은 결과가 나오도록 고정한다.

# 회고 문서의 날짜별 질문 수 (합계 229)
DAILY = {
    "2026-08-06": 6, "2026-08-11": 2, "2026-08-12": 1, "2026-08-13": 17,
    "2026-08-14": 8, "2026-08-15": 3, "2026-08-16": 6, "2026-08-17": 8,
    "2026-08-18": 40, "2026-08-19": 37, "2026-08-20": 15, "2026-08-21": 27,
    "2026-08-22": 7, "2026-08-23": 12, "2026-08-24": 30, "2026-08-25": 10,
}

# 회고 문서의 주제별 적중 수 (faq.md 제목 기준). '외 각 2건'과 '나머지 각 1건'은
# 회고에 이름이 없어 faq.md에서 그럴듯한 항목으로 채웠다. 합계 185.
TOPICS = {
    "시연 영상": 27, "IR Deck": 19, "서류 심사": 18, "가비아 서버": 11,
    "제출 항목": 9, "발표 규칙": 9, "트랙 피칭": 7, "부스 운영": 7, "개발 요건": 7,
    "일정": 5, "본선 토너먼트": 5, "심사 기준": 4, "식사": 4, "서비스 기획안": 4,
    "Kiro AWS 크레딧": 4, "주차": 3, "수료 기준": 3, "가비아 서버 생성": 3,
    "팀 빌딩": 2, "위치 교통": 2, "앱 배포 URL": 2,
    # 회고의 '외 각 2건'
    "깃허브 제출": 3, "행사 종료 시간": 2, "등록 출입": 2, "참가확인서": 2,
    "투표": 2, "상금 시상": 2, "멘토링": 2, "와이파이": 2,
    # 회고의 '나머지 13개 항목 각 1건'
    "대회 개요": 1, "문의 방법": 1, "참가비": 1, "트랙 선택": 1, "팀원 변경": 1,
    "팀명 변경": 1, "OpenAI 크레딧": 1, "교육 영상": 1, "좌석 짐": 1,
    "지각 조기퇴실": 1, "그라운드 룰": 1, "촬영": 1, "준비물": 1,
}

# 회고 문서에 공개된, LLM으로 넘어간 질문 표현 (31개)
LLM_PUBLIC = [
    "예선 제출", "심사 발표", "예선 발표", "결과", "언제끝남",
    "본선 전 예선은 어떻게 되나요", "예선과 본선은 누가 투표하거나 심사해?",
    "예선 2차의 발표와 본선의 첫 발표는 동일한가요",
    "8/24에 1차 심사결과 나온다 했는데 어디서 확인해", "본선발표", "본선 피칭",
    "몇시에 끝나", "행사시간", "시간", "해커톤 몇 시에 시작하나요?",
    "커피 사서 들고갈 수 있어?", "편의점", "배송", "부스 구성",
    "도메인은 지원안돼?", "도메인지원", "로컬로 프로덕트를 보여줘도 되는 경우는?",
    "제출해야하는 서류는 어떤 파일 형식이든?", "썸네일은 어디에 활용되나요?",
    "영상이 업로드가 되지 않는데 다른 방법?", "영상이 2분 초과면 감점? 예선탈락?",
    "본선행사 이후 퇴장 가능한 시간", "대표가 알아야하는것", "Build Guide", "수료질문",
    "ＩＲＤＥＣＫ",
]
# 회고에서 '가장 많이 샜다'고 한 예선·결과 확인 질문을 같은 결로 13건 더한다 (예시 문장).
LLM_EXTRA = [
    "예선 결과 어디서 확인해요?", "예선 결과 언제 나와요", "1차 심사 결과 어디서 봐요",
    "예선 제출은 어디로 하나요", "예선 통과하면 연락 오나요?", "결과 발표 몇 시예요?",
    "본선 진출 결과 어디서 확인", "예선 제출 마감 언제예요", "심사 결과 공지 채널이 어디예요",
    "해커톤 몇시에 끝나요?", "행사 몇 시에 끝나나요", "커피 들고 들어가도 돼요?",
    "도메인 지원해주나요?",
]
assert len(LLM_PUBLIC) + len(LLM_EXTRA) == 44

TEMPLATES = [
    "{t} 어떻게 돼요?", "{t} 관련해서 궁금한 게 있어요", "{t} 알려주세요",
    "{t} 확인하고 싶어요", "{t} 어디서 보면 되나요?", "{t} 기준이 뭐예요?",
]

N_USERS = 53


def _times_for_day(day: str, n: int, rng: random.Random) -> list:
    """하루 안에서 n개의 시각을 뽑는다. 낮~밤에 몰리고 새벽은 드물게."""
    base = datetime.datetime.strptime(day, "%Y-%m-%d")
    hours = list(range(24))
    weights = [1, 1, 0.5, 0.3, 0.2, 0.2, 0.3, 0.6, 1, 2, 3, 3.5,
               3, 3, 3.5, 3.5, 3, 3, 2.5, 3, 3.5, 3.5, 3, 2]
    out = []
    for _ in range(n):
        h = rng.choices(hours, weights)[0]
        out.append(base + datetime.timedelta(hours=h, minutes=rng.randrange(60), seconds=rng.randrange(60)))
    return sorted(out)


def build(rng: random.Random) -> tuple:
    users = [str(rng.randrange(10**17, 10**18)) for _ in range(N_USERS)]
    # 소수가 많이 묻는 분포 (몇 명이 질문의 상당수를 낸다)
    user_weights = [1 / (i + 1) ** 0.8 for i in range(N_USERS)]

    # 질문 목록: ('hit', 주제, 문장) / ('openai', None, 문장)
    items = []
    for topic, cnt in TOPICS.items():
        for _ in range(cnt):
            items.append(("hit", topic, rng.choice(TEMPLATES).format(t=topic)))
    for q in LLM_PUBLIC + LLM_EXTRA:
        items.append(("openai", None, q))
    rng.shuffle(items)
    assert len(items) == sum(DAILY.values()) == 229

    # 날짜별 시각을 만들어 질문에 순서대로 배정
    stamps = []
    for day, n in DAILY.items():
        stamps += _times_for_day(day, n, rng)
    stamps.sort()

    # 모든 사용자가 최소 한 번은 묻도록 앞에서 한 명씩 배정한 뒤 나머지는 가중치로
    who = users[:] + rng.choices(users, user_weights, k=len(items) - N_USERS)
    rng.shuffle(who)

    stats_lines, miss_lines = [], []
    for ts, uid, (kind, topic, q) in zip(stamps, who, items):
        t = ts.strftime("%Y-%m-%d %H:%M:%S")
        if kind == "hit":
            stats_lines.append(f"{t}\t{uid}\thit:{topic}\t{q}\n")
        else:
            stats_lines.append(f"{t}\t{uid}\topenai\t{q}\n")
            miss_lines.append(f"{t}\t[openai]\t{uid}\t{q}\n")
    return stats_lines, miss_lines


def main(argv: list) -> None:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "sample-data"
    out_dir.mkdir(parents=True, exist_ok=True)
    stats_lines, miss_lines = build(random.Random(SEED))
    (out_dir / "stats.log").write_text("".join(stats_lines), encoding="utf-8")
    (out_dir / "unanswered.log").write_text("".join(miss_lines), encoding="utf-8")
    print(f"예시 로그 생성: {out_dir}  (stats {len(stats_lines)}줄 / unanswered {len(miss_lines)}줄)")


if __name__ == "__main__":
    main(sys.argv)
