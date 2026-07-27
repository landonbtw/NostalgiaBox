"use server";

import { revalidatePath } from "next/cache";
import { requireSession } from "@/lib/auth/guard";
import { getSupabaseAdmin, isSupabaseConfigured } from "@/lib/supabase";
import { _clearRulesCache } from "@/lib/safety/rules-store";

function parsePatterns(raw: string): string[] {
  return raw
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

async function afterChange() {
  _clearRulesCache();
  revalidatePath("/dashboard/rules");
}

export async function saveRuleAction(formData: FormData): Promise<void> {
  await requireSession();
  if (!isSupabaseConfigured()) return;
  const id = String(formData.get("id") ?? "");
  const label = String(formData.get("label") ?? "").trim();
  const enabled = formData.get("enabled") === "on";
  const patterns = parsePatterns(String(formData.get("patterns") ?? ""));
  if (!id) return;

  const db = getSupabaseAdmin();
  await db.from("topic_rules").update({ label, enabled, patterns }).eq("id", id);
  await afterChange();
}

export async function addRuleAction(formData: FormData): Promise<void> {
  await requireSession();
  if (!isSupabaseConfigured()) return;
  const kind = String(formData.get("kind") ?? "");
  const rule_key = String(formData.get("rule_key") ?? "").trim().toLowerCase().replace(/\s+/g, "-");
  const label = String(formData.get("label") ?? "").trim();
  const patterns = parsePatterns(String(formData.get("patterns") ?? ""));
  if (!["allow", "deny", "refuse"].includes(kind) || !rule_key || !label) return;

  const db = getSupabaseAdmin();
  await db.from("topic_rules").upsert(
    { kind, rule_key, label, patterns, enabled: true, sort: 999 },
    { onConflict: "kind,rule_key" },
  );
  await afterChange();
}

export async function deleteRuleAction(formData: FormData): Promise<void> {
  await requireSession();
  if (!isSupabaseConfigured()) return;
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  const db = getSupabaseAdmin();
  await db.from("topic_rules").delete().eq("id", id);
  await afterChange();
}
