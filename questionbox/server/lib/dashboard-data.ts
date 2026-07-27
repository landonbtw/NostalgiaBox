import { getSupabaseAdmin, isSupabaseConfigured } from "./supabase";
import type { AnswerMode } from "./answer";

export interface Interaction {
  id: string;
  created_at: string;
  question: string | null;
  answer: string | null;
  mode: AnswerMode;
  category: string | null;
  reason: string | null;
  is_spelling: boolean;
  spell_word: string | null;
  latency_ms: number | null;
}

export interface TopicRuleRow {
  id: string;
  kind: "allow" | "deny" | "refuse";
  rule_key: string;
  label: string;
  patterns: string[];
  enabled: boolean;
  sort: number;
}

export interface DailySummary {
  date: string;
  total: number;
  answered: number;
  deferred: number;
  refused: number;
  topics: { label: string; count: number }[];
  friendly: string;
}

/** [start, end) ISO bounds for a YYYY-MM-DD day in the given tz offset (UTC). */
function dayBounds(date: string): { start: string; end: string } {
  const start = new Date(`${date}T00:00:00.000Z`);
  const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

export function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function getInteractionsByDay(date: string, q?: string): Promise<Interaction[]> {
  if (!isSupabaseConfigured()) return [];
  const db = getSupabaseAdmin();
  const { start, end } = dayBounds(date);
  let query = db
    .from("interactions")
    .select("*")
    .gte("created_at", start)
    .lt("created_at", end)
    .order("created_at", { ascending: false })
    .limit(500);
  if (q && q.trim()) {
    const term = q.trim().replace(/[%,]/g, " ");
    query = query.or(`question.ilike.%${term}%,answer.ilike.%${term}%`);
  }
  const { data, error } = await query;
  if (error) {
    console.error("[dashboard] getInteractionsByDay:", error);
    return [];
  }
  return (data ?? []) as Interaction[];
}

export async function getDailySummary(date: string): Promise<DailySummary> {
  const rows = await getInteractionsByDay(date);
  const summary: DailySummary = {
    date,
    total: rows.length,
    answered: rows.filter((r) => r.mode === "answered").length,
    deferred: rows.filter((r) => r.mode === "deferred").length,
    refused: rows.filter((r) => r.mode === "refused").length,
    topics: [],
    friendly: "",
  };

  const counts = new Map<string, number>();
  for (const r of rows) {
    if (r.mode === "answered" && r.category) {
      counts.set(r.category, (counts.get(r.category) ?? 0) + 1);
    }
  }
  summary.topics = [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);

  summary.friendly = buildFriendly(summary);
  return summary;
}

function buildFriendly(s: DailySummary): string {
  if (s.total === 0) return "No questions yet today.";
  const topicList = s.topics.map((t) => t.label).slice(0, 3);
  const topics = topicList.length
    ? ` about ${topicList.join(", ")}`
    : "";
  const parts = [`Today there were ${s.total} question${s.total === 1 ? "" : "s"}`];
  if (s.answered) parts.push(`answered ${s.answered}${topics}`);
  if (s.deferred) parts.push(`gently sent ${s.deferred} to a grown-up`);
  if (s.refused) parts.push(`declined ${s.refused}`);
  return parts.join(", ") + ".";
}

export async function getAllTopicRules(): Promise<TopicRuleRow[]> {
  if (!isSupabaseConfigured()) return [];
  const db = getSupabaseAdmin();
  const { data, error } = await db
    .from("topic_rules")
    .select("*")
    .order("kind", { ascending: true })
    .order("sort", { ascending: true });
  if (error) {
    console.error("[dashboard] getAllTopicRules:", error);
    return [];
  }
  return (data ?? []) as TopicRuleRow[];
}
