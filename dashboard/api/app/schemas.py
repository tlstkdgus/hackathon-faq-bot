# -*- coding: utf-8 -*-
"""API 응답 형식. FastAPI가 이걸로 /docs 문서와 응답 검증을 만든다."""

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    demo: bool = Field(description="예시 데이터로 띄운 시연 모드인지 (DASHBOARD_DEMO=1)")
    first_date: str | None
    last_date: str | None
    data_dir: str
    stats_log: bool = Field(description="stats.log 존재 여부")
    unanswered_log: bool = Field(description="unanswered.log 존재 여부")
    faq_entries: int
    skipped_lines: int = Field(description="형식이 맞지 않아 건너뛴 줄 수 (0이 아니면 로그 형식 점검 필요)")


class Summary(BaseModel):
    start: str | None
    end: str | None
    total: int
    unique_users: int
    faq: int = Field(description="키워드로 FAQ가 바로 답한 건수")
    llm: int = Field(description="LLM이 답한 건수")
    nomatch: int = Field(description="아무도 못 답한 건수")
    faq_rate: float = Field(description="FAQ 즉시 응답률 (0~1)")
    faq_entries: int
    faq_entries_used: int = Field(description="한 번 이상 적중한 FAQ 항목 수")
    busiest_day: str | None
    busiest_day_count: int


class DailyRow(BaseModel):
    date: str
    total: int
    faq: int
    llm: int
    nomatch: int


class HourlyRow(BaseModel):
    hour: int
    total: int


class TopicRow(BaseModel):
    topic: str
    count: int
    category: str | None


class QuestionRow(BaseModel):
    ts: str
    user: str
    route: str
    handled_by: str
    topic: str | None
    question: str


class QuestionPage(BaseModel):
    total: int
    items: list[QuestionRow]


class Suggestion(BaseModel):
    count: int = Field(description="비슷한 질문 수")
    sample: str
    others: list[str]
    nearest_entry: str | None = Field(description="가장 가까운 기존 FAQ 항목 (점수가 기준 미만이면 null → 새 항목 필요)")
    score: float
    keywords: list[str] = Field(description="해당 항목에 추가하면 좋을 키워드 후보")


class SuggestionReport(BaseModel):
    questions: int
    groups: int
    items: list[Suggestion]


class FaqHistoryRow(BaseModel):
    date: str
    entries: int


class FaqInfo(BaseModel):
    entries: int
    categories: list[dict]
    history: list[FaqHistoryRow]
