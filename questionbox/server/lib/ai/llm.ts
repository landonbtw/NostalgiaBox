import { getOpenAI } from "./openai";
import { buildAnswerSystemPrompt, buildClassifierPrompt } from "../safety/prompts";
import { DEFAULT_RULES, type SafetyRules } from "../safety/rules";

export interface LlmClassification {
  decision: "answer" | "defer" | "refuse";
  category?: string;
  reason?: string;
}

/** Gate 1: LLM classification. Defaults to "defer" on any parsing trouble. */
export async function classifyQuestion(
  question: string,
  rules: SafetyRules = DEFAULT_RULES,
): Promise<LlmClassification> {
  const openai = getOpenAI();
  const model = process.env.LLM_MODEL || "gpt-4o-mini";

  const res = await openai.chat.completions.create({
    model,
    temperature: 0,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: buildClassifierPrompt(rules) },
      { role: "user", content: question },
    ],
  });

  const txt = res.choices[0]?.message?.content ?? "{}";
  try {
    const j = JSON.parse(txt) as Partial<LlmClassification>;
    if (j.decision === "answer" || j.decision === "defer" || j.decision === "refuse") {
      return { decision: j.decision, category: j.category, reason: j.reason };
    }
  } catch {
    /* fall through to defer */
  }
  return { decision: "defer", reason: "classifier_parse_fallback" };
}

/** Gate 2: answer generation under the strict, kid-safe system prompt. */
export async function generateAnswer(
  question: string,
  rules: SafetyRules = DEFAULT_RULES,
): Promise<string> {
  const openai = getOpenAI();
  const model = process.env.LLM_MODEL || "gpt-4o-mini";

  const res = await openai.chat.completions.create({
    model,
    temperature: 0.4,
    max_tokens: 160,
    messages: [
      { role: "system", content: buildAnswerSystemPrompt(rules) },
      { role: "user", content: question },
    ],
  });

  return (res.choices[0]?.message?.content ?? "").trim();
}
