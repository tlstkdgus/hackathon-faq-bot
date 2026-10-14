// API 호출과 응답 타입. 타입은 FastAPI의 schemas.py와 1:1로 맞춘다.

export type Health = {
  status: string;
  demo: boolean;
  first_date: string | null;
  last_date: string | null;
  faq_entries: number;
  skipped_lines: number;
};

export type Summary = {
  total: number;
  unique_users: number;
  faq: number;
  llm: number;
  nomatch: number;
  faq_rate: number;
  faq_entries: number;
  faq_entries_used: number;
  busiest_day: string | null;
  busiest_day_count: number;
};

export type DailyRow = { date: string; total: number; faq: number; llm: number; nomatch: number };
export type HourlyRow = { hour: number; total: number };
export type TopicRow = { topic: string; count: number; category: string | null };
export type QuestionRow = {
  ts: string;
  user: string;
  route: "faq" | "llm" | "nomatch";
  handled_by: string;
  topic: string | null;
  question: string;
};
export type QuestionPage = { total: number; items: QuestionRow[] };
export type Suggestion = {
  count: number;
  sample: string;
  others: string[];
  nearest_entry: string | null;
  score: number;
  keywords: string[];
};
export type SuggestionReport = { questions: number; groups: number; items: Suggestion[] };
export type FaqInfo = { entries: number; history: { date: string; entries: number }[] };

export type Range = { start: string | null; end: string | null };

// 접근 토큰: 주소에 ?token=... 으로 한 번 들어오면 이 탭에서만 기억한다.
// 저장소가 막힌 환경(사생활 보호 모드 등)에서도 화면은 동작해야 하므로 try/catch.
const TOKEN_KEY = "faq-dashboard-token";

export function readToken(): string {
  const fromUrl = new URLSearchParams(window.location.search).get("token");
  if (fromUrl) {
    try {
      sessionStorage.setItem(TOKEN_KEY, fromUrl);
    } catch {
      /* 저장 실패해도 이번 요청에는 쓴다 */
    }
    return fromUrl;
  }
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* 무시 */
  }
}

export class UnauthorizedError extends Error {}

export async function get<T>(path: string, params: Record<string, string | number | null | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  }
  const url = `/api/${path}${qs.toString() ? `?${qs}` : ""}`;
  const res = await fetch(url, { headers: { "X-Dashboard-Token": readToken() } });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json() as Promise<T>;
}

export const rangeParams = (r: Range) => ({ start: r.start, end: r.end });
