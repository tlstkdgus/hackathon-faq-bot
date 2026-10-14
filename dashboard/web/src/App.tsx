import { useCallback, useEffect, useState } from "react";
import { UnauthorizedError, get, rangeParams, readToken, saveToken } from "./api";
import type { DailyRow, FaqInfo, Health, HourlyRow, Range, SuggestionReport, Summary, TopicRow } from "./api";
import { DailyChart, DailyTable, FaqHistoryChart, HourlyChart, Legend, TopicsChart } from "./components/Charts";
import { Questions, Suggestions, Tiles } from "./components/Panels";

type Data = {
  summary: Summary;
  daily: DailyRow[];
  hourly: HourlyRow[];
  topics: TopicRow[];
};

// 기간 프리셋. 로그는 지난 행사 기록일 수 있으므로 '오늘'이 아니라
// 데이터의 마지막 날짜를 기준으로 거슬러 올라간다.
const PRESETS = [
  { key: "all", label: "전체", days: null },
  { key: "14", label: "마지막 14일", days: 14 },
  { key: "7", label: "마지막 7일", days: 7 },
] as const;

const shift = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [faq, setFaq] = useState<FaqInfo | null>(null);
  const [range, setRange] = useState<Range>({ start: null, end: null });
  const [preset, setPreset] = useState<string>("all");
  const [data, setData] = useState<Data | null>(null);
  const [sugg, setSugg] = useState<SuggestionReport | null>(null);
  const [suggBusy, setSuggBusy] = useState(true);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [needToken, setNeedToken] = useState(false);
  const [tokenInput, setTokenInput] = useState(readToken());

  const onUnauthorized = useCallback(() => setNeedToken(true), []);

  useEffect(() => {
    get<Health>("health").then(setHealth).catch(() => setError("API에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요."));
  }, []);

  useEffect(() => {
    if (needToken) return;
    get<FaqInfo>("faq").then(setFaq).catch((e) => e instanceof UnauthorizedError && setNeedToken(true));
  }, [needToken]);

  // 기간이 바뀌면 아래 모든 지표·차트를 같은 기간으로 다시 불러온다.
  // 불러오는 동안에는 이전 화면을 흐리게 유지한다 (레이아웃이 튀지 않게).
  useEffect(() => {
    if (needToken) return;
    let alive = true;
    setBusy(true);
    const p = rangeParams(range);
    Promise.all([
      get<Summary>("summary", p),
      get<DailyRow[]>("daily", p),
      get<HourlyRow[]>("hourly", p),
      get<TopicRow[]>("topics", { ...p, limit: 10 }),
    ])
      .then(([summary, daily, hourly, topics]) => {
        if (!alive) return;
        setData({ summary, daily, hourly, topics });
        setError("");
      })
      .catch((e) => {
        if (e instanceof UnauthorizedError) setNeedToken(true);
        else setError("데이터를 불러오지 못했습니다.");
      })
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [range, needToken]);

  // 'FAQ 보완 후보'는 질문을 묶는 계산이 무거워(첫 계산 수 초) 따로 불러온다.
  // 그래야 나머지 지표가 이 계산을 기다리지 않는다.
  useEffect(() => {
    if (needToken) return;
    let alive = true;
    setSuggBusy(true);
    get<SuggestionReport>("suggestions", { ...rangeParams(range), limit: 8 })
      .then((d) => alive && setSugg(d))
      .catch((e) => e instanceof UnauthorizedError && setNeedToken(true))
      .finally(() => alive && setSuggBusy(false));
    return () => {
      alive = false;
    };
  }, [range, needToken]);

  const choosePreset = (key: string, days: number | null) => {
    setPreset(key);
    if (days === null || !health?.last_date) setRange({ start: null, end: null });
    else setRange({ start: shift(health.last_date, days - 1), end: health.last_date });
  };

  if (needToken) {
    return (
      <div className="wrap">
        <div className="card login">
          <h2>접근 토큰이 필요합니다</h2>
          <p className="sub">운영진에게 받은 현황판 토큰을 입력해 주세요.</p>
          <input type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} aria-label="접근 토큰" />
          <button onClick={() => { saveToken(tokenInput); setNeedToken(false); }}>확인</button>
        </div>
      </div>
    );
  }

  const s = data?.summary;
  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>FAQ 봇 운영 현황판</h1>
          <p>멋쟁이사자처럼 14기 중앙해커톤 · 디스코드 FAQ 봇 질문 로그 기준</p>
        </div>
        {health?.demo && <span className="badge">예시 데이터 · 운영 회고의 실제 집계로 재구성</span>}
      </header>

      {error && <div className="error">{error}</div>}
      {health && health.skipped_lines > 0 && (
        <div className="error">로그에서 형식이 맞지 않는 줄 {health.skipped_lines}개를 건너뛰었습니다. 로그 형식을 점검해 주세요.</div>
      )}

      <div className="filters" role="group" aria-label="기간">
        <div className="seg">
          {PRESETS.map((p) => (
            <button key={p.key} aria-pressed={preset === p.key} onClick={() => choosePreset(p.key, p.days)}>{p.label}</button>
          ))}
        </div>
        <input type="date" aria-label="시작일" value={range.start ?? ""} min={health?.first_date ?? undefined} max={health?.last_date ?? undefined}
          onChange={(e) => { setPreset("custom"); setRange({ ...range, start: e.target.value || null }); }} />
        <span className="hint">~</span>
        <input type="date" aria-label="종료일" value={range.end ?? ""} min={health?.first_date ?? undefined} max={health?.last_date ?? undefined}
          onChange={(e) => { setPreset("custom"); setRange({ ...range, end: e.target.value || null }); }} />
        {health?.first_date && <span className="hint">기록 기간 {health.first_date} ~ {health.last_date}</span>}
      </div>

      {!s && !error && <div className="empty">불러오는 중…</div>}
      {s && data && (
        <div className={busy ? "loading" : ""}>
          <Tiles s={s} />
          <div className="grid">
            <section className="card span-8">
              <h2>날짜별 질문 수</h2>
              <p className="sub">응답 경로별로 나눠 봅니다. 문의가 몰리는 시점에 FAQ가 준비돼 있었는지 확인할 수 있습니다.</p>
              <Legend />
              {data.daily.length ? <DailyChart rows={data.daily} /> : <div className="empty">이 기간에는 질문이 없어요.</div>}
              {data.daily.length > 0 && <DailyTable rows={data.daily} />}
            </section>
            <section className="card span-4">
              <h2>많이 물은 FAQ 주제</h2>
              <p className="sub">키워드로 바로 답한 질문 기준 상위 10개</p>
              {data.topics.length ? <TopicsChart rows={data.topics} /> : <div className="empty">FAQ로 답한 질문이 없어요.</div>}
            </section>
            <section className="card span-6">
              <h2>시간대별 질문 수</h2>
              <p className="sub">운영진이 대기해야 할 시간대</p>
              <HourlyChart rows={data.hourly} />
            </section>
            <section className="card span-6">
              <h2>FAQ 항목 수 추이</h2>
              <p className="sub">faq.md 변경 기록(git) 기준 · 현재 {faq?.entries ?? "-"}개</p>
              {faq?.history.length ? <FaqHistoryChart rows={faq.history} /> : <div className="empty">추이 기록이 없어요.</div>}
            </section>
            <section className={`card span-6 ${suggBusy ? "loading" : ""}`}>
              <h2>FAQ 보완 후보</h2>
              {sugg ? <Suggestions items={sugg.items} questions={sugg.questions} /> : <div className="empty">질문을 묶는 중…</div>}
            </section>
            <section className="card span-6">
              <h2>질문 검색</h2>
              <p className="sub">사용자 ID는 별칭으로만 표시됩니다.</p>
              <Questions range={range} onUnauthorized={onUnauthorized} />
            </section>
          </div>
        </div>
      )}
      <footer>
        API 문서: <a href="/docs">/docs</a> · 로그 형식과 집계 기준은 봇과 동일 (stats_engine · digest 재사용)
      </footer>
    </div>
  );
}
