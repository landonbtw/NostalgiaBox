/**
 * Interaction logging. We store ONLY text: the timestamp, the transcribed
 * question, the answer, whether it was answered/refused/deferred, and why.
 * Audio is NEVER logged or stored. Logging is best-effort — a logging failure
 * must never break a child's answer.
 */
import { getSupabaseAdmin, isSupabaseConfigured } from "./supabase";
import type { AnswerMode } from "./answer";

export interface InteractionLog {
  question: string;
  answer: string;
  mode: AnswerMode;
  category?: string;
  reason?: string;
  isSpelling: boolean;
  spellWord?: string;
  latencyMs?: number;
  deviceId?: string;
}

export async function logInteraction(entry: InteractionLog): Promise<void> {
  if (!isSupabaseConfigured()) return; // logging is optional
  try {
    const db = getSupabaseAdmin();
    const { error } = await db.from("interactions").insert({
      question: entry.question,
      answer: entry.answer,
      mode: entry.mode,
      category: entry.category ?? null,
      reason: entry.reason ?? null,
      is_spelling: entry.isSpelling,
      spell_word: entry.spellWord ?? null,
      latency_ms: entry.latencyMs ?? null,
      device_id: entry.deviceId ?? null,
    });
    if (error) throw error;
  } catch (e) {
    console.error("[log] failed to write interaction:", e);
  }
}
