/**
 * The WonderBox answer pipeline — the safety orchestrator.
 *
 * Layers (a bad answer must beat ALL of them; we default to DEFER when unsure):
 *   Gate 0  deterministic rule check (blocked topics never reach an LLM)
 *   (spelling handled deterministically and safely)
 *   Gate 1  LLM classifier — anything but a clear "answer" => defer
 *   Gate 2  answer LLM under a strict kid-safe system prompt (can emit [DEFER])
 *   post    deterministic re-check of the generated answer + length clamp
 *
 * LLM access is injected via `deps` so this whole file is unit-testable with no
 * network and no API keys.
 */
import { containsBlockedContent, detectSpelling, ruleCheck } from "./safety/classifier";
import { deferMessage, refuseMessage } from "./safety/messages";
import { DEFER_TOKEN } from "./safety/prompts";
import type { AnswerMode } from "./answer";

export interface PipelineResult {
  text: string;
  mode: AnswerMode;
  isSpelling: boolean;
  spellWord?: string;
  category?: string;
  reason?: string;
}

export interface PipelineDeps {
  classify: (question: string) => Promise<{ decision: "answer" | "defer" | "refuse"; category?: string; reason?: string }>;
  generate: (question: string) => Promise<string>;
}

const MAX_SENTENCES = 3;
const MAX_CHARS = 280;

function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

function clampSentences(text: string): string {
  const trimmed = text.replace(/\s+/g, " ").trim();
  const parts = trimmed.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [trimmed];
  let out = parts.slice(0, MAX_SENTENCES).join(" ").trim();
  if (out.length > MAX_CHARS) out = out.slice(0, MAX_CHARS).trim();
  return out;
}

function defer(seed: string, reason?: string, category?: string): PipelineResult {
  return { text: deferMessage(seed), mode: "deferred", isSpelling: false, category, reason };
}

function refuse(reason?: string, category?: string): PipelineResult {
  return { text: refuseMessage(), mode: "refused", isSpelling: false, category, reason };
}

export async function answerQuestion(question: string, deps: PipelineDeps): Promise<PipelineResult> {
  const q = (question ?? "").trim();
  if (!q) return defer("empty", "empty_question");

  // --- Gate 0: deterministic rules (hard block; never reaches an LLM) ---
  const rule = ruleCheck(q);
  if (rule.decision === "refuse") return refuse(rule.reason, rule.category);
  if (rule.decision === "defer") return defer(q, rule.reason, rule.category);

  // --- Spelling: deterministic and safe (only spells the requested word) ---
  const spellWord = detectSpelling(q);
  if (spellWord) {
    if (containsBlockedContent(spellWord)) return defer(q, "blocked_spell_word");
    const letters = spellWord.toUpperCase().split("").join(", ");
    return {
      text: `"${cap(spellWord)}" is spelled ${letters}. ${cap(spellWord)}!`,
      mode: "answered",
      isSpelling: true,
      spellWord: spellWord.toUpperCase(),
      category: "spelling",
    };
  }

  // --- Gate 1: LLM classifier (default to defer on anything but "answer") ---
  let cls: { decision: "answer" | "defer" | "refuse"; category?: string; reason?: string };
  try {
    cls = await deps.classify(q);
  } catch {
    return defer(q, "classify_error");
  }
  if (cls.decision === "refuse") return refuse(cls.reason ?? "llm_refuse", cls.category);
  if (cls.decision !== "answer") return defer(q, cls.reason ?? "llm_defer", cls.category);

  // --- Gate 2: answer model under the strict system prompt ---
  let raw: string;
  try {
    raw = await deps.generate(q);
  } catch {
    return defer(q, "generate_error", cls.category);
  }
  const ans = (raw ?? "").trim();
  if (!ans || ans.includes(DEFER_TOKEN)) return defer(q, "model_deferred", cls.category);

  // --- Post-check: the generated answer must itself be clean and short ---
  if (containsBlockedContent(ans)) return defer(q, "answer_tripped_deny", cls.category);
  const clean = clampSentences(ans);
  if (!clean) return defer(q, "empty_after_clamp", cls.category);

  return { text: clean, mode: "answered", isSpelling: false, category: cls.category, reason: cls.reason };
}
