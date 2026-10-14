import {
  Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { DailyRow, HourlyRow, TopicRow } from "../api";

// 응답 경로 = 범주(정체성). 색은 고정 순서로 배정하고, 필터로 바뀌지 않는다.
export const ROUTES = [
  { key: "faq", label: "FAQ 즉시 응답", color: "var(--series-1)" },
  { key: "llm", label: "LLM 응답", color: "var(--series-2)" },
  { key: "nomatch", label: "미응답", color: "var(--series-3)" },
] as const;

const AXIS = { fontSize: 12, fill: "var(--muted)" };
const md = (iso: string) => {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
};

export function Legend() {
  return (
    <div className="legend" aria-hidden="true">
      {ROUTES.map((r) => (
        <span key={r.key}>
          <i style={{ background: r.color }} />
          {r.label}
        </span>
      ))}
    </div>
  );
}

/* ── 날짜별: 응답 경로 누적 막대 ───────────────────────────────── */

type SegProps = {
  x?: number; y?: number; width?: number; height?: number; fill?: string;
  payload?: DailyRow; dataKey?: string;
};

// 누적 막대의 한 조각. 맨 위 조각만 위쪽 모서리를 4px 둥글게 하고,
// 아래 조각과 닿는 쪽은 2px 비워(표면색 틈) 테두리 없이 구분한다.
function Segment({ x = 0, y = 0, width = 0, height = 0, fill, payload, dataKey }: SegProps) {
  if (!payload || height <= 0) return null;
  const order = ROUTES.map((r) => r.key).filter((k) => payload[k] > 0);
  const isTop = order[order.length - 1] === dataKey;
  const isBottom = order[0] === dataKey;
  const h = isBottom ? height : Math.max(height - 2, 0.5);
  const r = isTop ? Math.min(4, width / 2, h) : 0;
  const path = `M${x},${y + h} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + width - r},${y} Q${x + width},${y} ${x + width},${y + r} L${x + width},${y + h} Z`;
  return <path d={path} fill={fill} />;
}

function DailyTip({ active, payload }: { active?: boolean; payload?: { payload: DailyRow }[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="tip">
      <div className="head">{row.date} · 합계 <b>{row.total}</b>건</div>
      {ROUTES.map((r) => (
        <div className="row" key={r.key}>
          <b>{row[r.key]}</b>
          <i className="key" style={{ background: r.color }} />
          <span>{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export function DailyChart({ rows }: { rows: DailyRow[] }) {
  // 가장 많은 날 하나에만 값 라벨을 단다 (모든 막대에 숫자를 달지 않는다)
  const peak = rows.reduce((m, r) => (r.total > m ? r.total : m), 0);
  // 라벨은 '그날의 맨 위 조각' 위에 붙여야 하므로, 위치는 마지막 계열 기준으로 계산한다.
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ top: 20, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="date" tickFormatter={md} tick={AXIS} axisLine={{ stroke: "var(--axis)" }} tickLine={false} minTickGap={8} />
        <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
        <Tooltip content={<DailyTip />} cursor={{ fill: "var(--wash)" }} />
        {ROUTES.map((r, i) => (
          <Bar key={r.key} dataKey={r.key} stackId="d" fill={r.color} maxBarSize={24}
            shape={<Segment />} isAnimationActive={false}>
            {i === ROUTES.length - 1 && <LabelList dataKey="total" content={peakTopLabel(rows, peak)} />}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// 누적 막대 맨 위 좌표를 직접 계산해 최고점 라벨을 단다.
// (LabelList는 '마지막 계열' 조각 기준 좌표를 주는데, 그 조각이 0이면 높이가 0이라
//  y가 곧 누적 꼭대기가 된다 — 그래서 마지막 계열에 붙이면 항상 맨 위에 놓인다.)
function peakTopLabel(rows: DailyRow[], peak: number) {
  return function Label(props: { x?: number | string; y?: number | string; width?: number | string; index?: number }) {
    const x = Number(props.x ?? 0), y = Number(props.y ?? 0), w = Number(props.width ?? 0);
    const row = rows[props.index ?? -1];
    if (!row || peak === 0 || row.total !== peak) return null;
    return (
      <text x={x + w / 2} y={y - 6} textAnchor="middle" fontSize={12} fill="var(--ink-2)">
        최다 {peak}건
      </text>
    );
  };
}

export function DailyTable({ rows }: { rows: DailyRow[] }) {
  return (
    <details className="table-view">
      <summary>표로 보기</summary>
      <table>
        <thead>
          <tr><th>날짜</th>{ROUTES.map((r) => <th className="num" key={r.key}>{r.label}</th>)}<th className="num">합계</th></tr>
        </thead>
        <tbody>
          {rows.filter((r) => r.total > 0).map((r) => (
            <tr key={r.date}>
              <td>{r.date}</td>
              {ROUTES.map((x) => <td className="num" key={x.key}>{r[x.key]}</td>)}
              <td className="num">{r.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

/* ── 시간대별: 단일 계열 막대 ─────────────────────────────────── */

function SimpleTip({ active, payload, label, unit }: { active?: boolean; payload?: { value: number }[]; label?: string | number; unit: (l: string | number | undefined) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      <div className="row"><b>{payload[0].value}</b><span>건</span></div>
      <div className="head" style={{ margin: 0 }}>{unit(label)}</div>
    </div>
  );
}

export function HourlyChart({ rows }: { rows: HourlyRow[] }) {
  const peak = Math.max(0, ...rows.map((r) => r.total));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} margin={{ top: 20, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="hour" tickFormatter={(h) => `${h}시`} tick={AXIS} axisLine={{ stroke: "var(--axis)" }} tickLine={false} interval={2} />
        <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
        <Tooltip content={<SimpleTip unit={(h) => `${h}시~${Number(h) + 1}시`} />} cursor={{ fill: "var(--wash)" }} />
        <Bar dataKey="total" fill="var(--series-1)" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
          <LabelList dataKey="total" content={(p: { x?: number | string; y?: number | string; width?: number | string; value?: number | string }) =>
            Number(p.value) === peak && peak > 0 ? (
              <text x={Number(p.x) + Number(p.width) / 2} y={Number(p.y) - 6} textAnchor="middle" fontSize={12} fill="var(--ink-2)">{peak}건</text>
            ) : null} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── 주제별: 가로 막대 ────────────────────────────────────────── */

export function TopicsChart({ rows }: { rows: TopicRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 30 + 10)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis type="category" dataKey="topic" width={112} tick={{ fontSize: 12, fill: "var(--ink-2)" }} axisLine={{ stroke: "var(--axis)" }} tickLine={false} />
        <Tooltip content={<SimpleTip unit={(t) => String(t)} />} cursor={{ fill: "var(--wash)" }} />
        <Bar dataKey="count" fill="var(--series-1)" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          <LabelList dataKey="count" position="right" fontSize={12} fill="var(--ink-2)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ── FAQ 항목 수 추이: 계단 선 ────────────────────────────────── */

export function FaqHistoryChart({ rows }: { rows: { date: string; entries: number }[] }) {
  // 날짜 간격이 고르지 않으므로(커밋한 날만 있음) 범주가 아니라 시간 축으로 그린다.
  const data = rows.map((r) => ({ ...r, t: new Date(`${r.date}T00:00:00`).getTime() }));
  const last = data.length - 1;
  // 눈금은 25 단위의 깔끔한 숫자로 (0 / 25 / 50 / 75 / 100)
  const top = Math.max(25, Math.ceil((Math.max(...rows.map((r) => r.entries)) + 1) / 25) * 25);
  const ticks = Array.from({ length: top / 25 + 1 }, (_, i) => i * 25);
  const fmtLabel = (t: number) => {
    const d = new Date(t);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 20, right: 36, bottom: 0, left: -16 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => md(fmtLabel(t))}
          tick={AXIS} axisLine={{ stroke: "var(--axis)" }} tickLine={false} minTickGap={16} />
        <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} domain={[0, top]} ticks={ticks} />
        <Tooltip content={<SimpleTip unit={(t) => `${fmtLabel(Number(t))} 기준 FAQ 항목 수`} />} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} />
        <Line type="stepAfter" dataKey="entries" stroke="var(--series-1)" strokeWidth={2} isAnimationActive={false}
          dot={(p: { cx?: number; cy?: number; index?: number }) =>
            p.index === last ? <circle key="end" cx={p.cx} cy={p.cy} r={4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} /> : <g key={p.index} />}
          activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}>
          <LabelList dataKey="entries" content={(p: { x?: number | string; y?: number | string; index?: number; value?: number | string }) =>
            p.index === last ? <text x={Number(p.x) + 8} y={Number(p.y) + 4} fontSize={12} fill="var(--ink-2)">{p.value}개</text> : null} />
        </Line>
      </LineChart>
    </ResponsiveContainer>
  );
}
