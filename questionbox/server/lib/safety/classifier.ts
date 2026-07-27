/**
 * Deterministic, rule-based safety classifier (defense-in-depth gate).
 *
 * This runs BEFORE any LLM call and is the layer the safety test-suite pins
 * down: blocked/deferred categories are caught here regardless of what any LLM
 * does. It complements (does not replace) the two LLM gates.
 */
import { DEFAULT_RULES, type SafetyRules, type TopicRule } from "./rules";

export type RuleDecision = "answer" | "defer" | "refuse" | "unknown";

export interface RuleVerdict {
  decision: RuleDecision;
  category?: string;
  reason?: string;
}

function matchAny(rules: TopicRule[], text: string): TopicRule | undefined {
  for (const rule of rules) {
    for (const p of rule.patterns) {
      let re: RegExp;
      try {
        re = new RegExp(p, "i");
      } catch {
        continue; // ignore a malformed pattern rather than crash
      }
      if (re.test(text)) return rule;
    }
  }
  return undefined;
}

/**
 * Classify a question using only the rules. Order matters:
 *   1. refuse (jailbreak / rule-change attempts)
 *   2. deny (always defer to a parent)
 *   3. allow (candidate to answer — still subject to the LLM gates)
 *   4. unknown (no rule matched)
 */
export function ruleCheck(question: string, rules: SafetyRules = DEFAULT_RULES): RuleVerdict {
  const text = (question ?? "").toLowerCase().trim();
  if (!text) return { decision: "defer", reason: "empty question" };

  const refused = matchAny(rules.refuse, text);
  if (refused) return { decision: "refuse", category: refused.label, reason: `matched refuse:${refused.id}` };

  const denied = matchAny(rules.deny, text);
  if (denied) return { decision: "defer", category: denied.label, reason: `matched deny:${denied.id}` };

  const allowed = matchAny(rules.allow, text);
  if (allowed) return { decision: "answer", category: allowed.label, reason: `matched allow:${allowed.id}` };

  return { decision: "unknown", reason: "no rule matched" };
}

/** True if the text trips any deny/refuse rule — used to vet generated answers. */
export function containsBlockedContent(text: string, rules: SafetyRules = DEFAULT_RULES): boolean {
  const v = ruleCheck(text, rules);
  return v.decision === "defer" || v.decision === "refuse";
}

/**
 * Detect a spelling request and extract the word to spell.
 * Returns the lowercase word, or null if this isn't a spelling question.
 */
export function detectSpelling(question: string): string | null {
  const q = (question ?? "").trim();
  const patterns = [
    /how\s+do\s+you\s+spell\s+(?:the\s+word\s+)?["']?([a-zA-Z]{1,20})/i,
    /how\s+to\s+spell\s+(?:the\s+word\s+)?["']?([a-zA-Z]{1,20})/i,
    /can\s+you\s+spell\s+(?:the\s+word\s+)?["']?([a-zA-Z]{1,20})/i,
    /^\s*spell\s+(?:the\s+word\s+)?["']?([a-zA-Z]{1,20})/i,
  ];
  for (const re of patterns) {
    const m = re.exec(q);
    if (m && m[1]) return m[1].toLowerCase();
  }
  return null;
}
