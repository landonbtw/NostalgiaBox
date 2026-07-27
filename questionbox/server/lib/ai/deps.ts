import type { PipelineDeps } from "../pipeline";
import type { SafetyRules } from "../safety/rules";
import { classifyQuestion, generateAnswer } from "./llm";

/**
 * Build the real (OpenAI-backed) pipeline dependencies bound to a specific set
 * of safety rules (so the LLM prompts match the editable configuration).
 */
export function makeRealDeps(rules: SafetyRules): PipelineDeps {
  return {
    classify: (q) => classifyQuestion(q, rules),
    generate: (q) => generateAnswer(q, rules),
  };
}
