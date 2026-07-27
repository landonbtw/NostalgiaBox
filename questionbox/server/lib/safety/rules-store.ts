/**
 * Loads the editable safety rules from Supabase (so a parent can change them
 * from the dashboard without a code change). Falls back to DEFAULT_RULES when
 * Supabase isn't configured, and seeds the table with the defaults the first
 * time it's found empty. Cached briefly to avoid a DB hit on every question.
 */
import { getSupabaseAdmin, isSupabaseConfigured } from "../supabase";
import { DEFAULT_RULES, type SafetyRules, type TopicRule } from "./rules";

interface RuleRow {
  kind: "allow" | "deny" | "refuse";
  rule_key: string;
  label: string;
  patterns: string[];
  enabled: boolean;
  sort: number;
}

const CACHE_TTL_MS = 30_000;
let cache: { rules: SafetyRules; at: number } | null = null;

export function rulesToRows(rules: SafetyRules): RuleRow[] {
  const rows: RuleRow[] = [];
  const push = (kind: RuleRow["kind"], list: TopicRule[]) =>
    list.forEach((r, i) =>
      rows.push({ kind, rule_key: r.id, label: r.label, patterns: r.patterns, enabled: true, sort: i }),
    );
  push("allow", rules.allow);
  push("deny", rules.deny);
  push("refuse", rules.refuse);
  return rows;
}

function rowsToRules(rows: RuleRow[]): SafetyRules {
  const pick = (kind: RuleRow["kind"]): TopicRule[] =>
    rows
      .filter((r) => r.kind === kind && r.enabled)
      .sort((a, b) => a.sort - b.sort)
      .map((r) => ({ id: r.rule_key, label: r.label, patterns: r.patterns ?? [] }));
  return {
    version: "supabase",
    allow: pick("allow"),
    deny: pick("deny"),
    refuse: pick("refuse"),
  };
}

/** Returns the current safety rules, from Supabase if configured else defaults. */
export async function getRules(): Promise<SafetyRules> {
  if (!isSupabaseConfigured()) return DEFAULT_RULES;

  if (cache && Date.now() - cache.at < CACHE_TTL_MS) return cache.rules;

  try {
    const db = getSupabaseAdmin();
    const { data, error } = await db.from("topic_rules").select("kind,rule_key,label,patterns,enabled,sort");
    if (error) throw error;

    let rows = (data ?? []) as RuleRow[];
    if (rows.length === 0) {
      // First run: seed the table with the defaults.
      await db.from("topic_rules").upsert(rulesToRows(DEFAULT_RULES), { onConflict: "kind,rule_key" });
      rows = rulesToRows(DEFAULT_RULES);
    }

    const rules = rowsToRules(rows);
    // Guard against a misconfigured/empty allow list wiping our safety net:
    // if there are no deny rules, fall back to defaults.
    if (rules.deny.length === 0) {
      cache = { rules: DEFAULT_RULES, at: Date.now() };
      return DEFAULT_RULES;
    }
    cache = { rules, at: Date.now() };
    return rules;
  } catch (e) {
    console.error("[rules] load failed, using defaults:", e);
    return DEFAULT_RULES;
  }
}

/** Seeds the topic_rules table with the defaults if it is empty. Safe to call
 *  repeatedly. Used by the dashboard so the editor is populated on first visit. */
export async function ensureRulesSeeded(): Promise<void> {
  if (!isSupabaseConfigured()) return;
  const db = getSupabaseAdmin();
  const { count, error } = await db.from("topic_rules").select("id", { count: "exact", head: true });
  if (error) throw error;
  if ((count ?? 0) === 0) {
    await db.from("topic_rules").upsert(rulesToRows(DEFAULT_RULES), { onConflict: "kind,rule_key" });
  }
}

/** Invalidate the in-memory cache after a rules edit (or in tests). */
export function _clearRulesCache(): void {
  cache = null;
}
