import { useEffect, useState } from "react";
import { UnauthorizedError, get, rangeParams } from "../api";
import type { QuestionPage, Range, Suggestion, Summary } from "../api";
import { ROUTES } from "./Charts";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const fmt = (n: number) => n.toLocaleString("ko-KR");

/* ── 핵심 지표 타일 ───────────────────────────────────────────── */

export function Tiles({ s }: { s: Summary }) {
  return (
    <section className="tiles" aria-label="핵심 지표">
      <div className="tile hero">
        <div className="label">FAQ 즉시 응답률</div>
        <div className="value">{pct(s.faq_rate)}</div>
        <div className="note">전체 {fmt(s.total)}건 중 {fmt(s.faq)}건을 키워드 FAQ로 바로 답함</div>
      </div>
      <div className="tile">
        <div className="label">총 질문</div>
        <div className="value">{fmt(s.total)}건</div>
        <div className="note">사용 인원 {fmt(s.unique_users)}명</div>
      </div>
      <div className="tile">
        <div className="label">LLM 응답</div>
        <div className="value">{fmt(s.llm)}건</div>
        <div className="note">FAQ 보완 대상</div>
      </div>
      <div className="tile">
        <div className="label">미응답</div>
        <div className="value">{fmt(s.nomatch)}건</div>
        <div className="note">FAQ·LLM 모두 실패</div>
      </div>
      <div className="tile">
        <div className="label">적중한 FAQ 항목</div>
        <div className="value">{s.faq_entries_used} / {s.faq_entries}</div>
        <div className="note">{s.busiest_day ? `최다 질문일 ${s.busiest_day} (${s.busiest_day_count}건)` : "질문 없음"}</div>
      </div>
    </section>
  );
}

/* ── FAQ 보완 후보 (봇의 일일 리포트와 같은 분석) ───────────────── */

export function Suggestions({ items, questions }: { items: Suggestion[]; questions: number }) {
  if (!items.length) return <div className="empty">이 기간에는 키워드가 못 잡은 질문이 없어요.</div>;
  return (
    <>
      <p className="sub">키워드가 못 잡은 질문 {questions}건을 비슷한 것끼리 묶었습니다. 반영 여부는 운영진이 판단합니다.</p>
      <ul className="sugg">
        {items.map((s, i) => (
          <li key={i}>
            <div className="q">
              “{s.sample}”{s.count > 1 && <span className="cnt">비슷한 질문 {s.count}건</span>}
            </div>
            {s.others.length > 0 && <p className="others">{s.others.map((o) => `“${o}”`).join(" · ")}</p>}
            <div className="meta">
              {s.nearest_entry ? <span>가까운 항목: <b>{s.nearest_entry}</b></span> : <span className="new">맞는 항목 없음 · 새 항목 필요</span>}
              {s.keywords.length > 0 && <span>키워드 후보</span>}
              {s.keywords.map((k) => <span className="chip" key={k}>{k}</span>)}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

/* ── 질문 검색 표 ─────────────────────────────────────────────── */

const PAGE = 15;

export function Questions({ range, onUnauthorized }: { range: Range; onUnauthorized: () => void }) {
  const [q, setQ] = useState("");
  const [route, setRoute] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<QuestionPage | null>(null);
  const [busy, setBusy] = useState(false);

  // 검색어·필터·기간이 바뀌면 첫 페이지로
  useEffect(() => setOffset(0), [q, route, range.start, range.end]);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    const t = setTimeout(() => {
      get<QuestionPage>("questions", { ...rangeParams(range), q, route, limit: PAGE, offset })
        .then((d) => alive && setData(d))
        .catch((e) => { if (e instanceof UnauthorizedError) onUnauthorized(); })
        .finally(() => alive && setBusy(false));
    }, 200); // 타이핑 중에는 요청을 아낀다
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [q, route, offset, range.start, range.end, onUnauthorized]);

  const color = (r: string) => ROUTES.find((x) => x.key === r)?.color;
  const name = (r: string) => ROUTES.find((x) => x.key === r)?.label ?? r;

  return (
    <div className={busy ? "loading" : ""}>
      <div className="toolbar">
        <input type="search" placeholder="질문 검색 (예: 예선 결과)" value={q} onChange={(e) => setQ(e.target.value)} aria-label="질문 검색" />
        <select value={route} onChange={(e) => setRoute(e.target.value)} aria-label="응답 경로">
          <option value="">모든 응답 경로</option>
          {ROUTES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
      </div>
      {data && data.items.length === 0 && <div className="empty">조건에 맞는 질문이 없어요.</div>}
      {data && data.items.length > 0 && (
        <table className="qtable">
          <thead>
            <tr><th>시각</th><th>질문</th><th>응답 경로</th><th>사용자</th></tr>
          </thead>
          <tbody>
            {data.items.map((r, i) => (
              <tr key={`${r.ts}-${i}`}>
                <td className="when">{r.ts}</td>
                <td className="q">{r.question || <span style={{ color: "var(--muted)" }}>(원문 미기록)</span>}</td>
                <td>
                  <span className="route"><i style={{ background: color(r.route) }} />{r.topic ? r.topic : name(r.route)}</span>
                </td>
                <td className="when who">{r.user}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.total > PAGE && (
        <div className="pager">
          <span>{fmt(data.total)}건 중 {offset + 1}–{Math.min(offset + PAGE, data.total)}</span>
          <span>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>이전</button>{" "}
            <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>다음</button>
          </span>
        </div>
      )}
    </div>
  );
}
