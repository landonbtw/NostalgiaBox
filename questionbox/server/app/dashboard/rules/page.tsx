import { ensureRulesSeeded } from "@/lib/safety/rules-store";
import { getAllTopicRules, type TopicRuleRow } from "@/lib/dashboard-data";
import { isSupabaseConfigured } from "@/lib/supabase";
import { addRuleAction, deleteRuleAction, saveRuleAction } from "./actions";

export const dynamic = "force-dynamic";

const KIND_TITLE: Record<TopicRuleRow["kind"], string> = {
  allow: "Allowed topics (answered)",
  deny: "Deferred topics (sent to a grown-up)",
  refuse: "Refused (rule-change attempts)",
};

const KIND_HELP: Record<TopicRuleRow["kind"], string> = {
  allow: "Questions matching these may be answered (still checked by the AI safety gates).",
  deny: "Questions matching these are always sent to a parent — never answered.",
  refuse: "Attempts to change the rules or jailbreak the box.",
};

function RuleCard({ rule }: { rule: TopicRuleRow }) {
  return (
    <div className={`rule ${rule.enabled ? "" : "rule-off"}`}>
      <form action={saveRuleAction} className="rule-form">
        <input type="hidden" name="id" value={rule.id} />
        <div className="rule-head">
          <input className="input rule-label" name="label" defaultValue={rule.label} aria-label="Topic label" />
          <label className="switch">
            <input type="checkbox" name="enabled" defaultChecked={rule.enabled} /> on
          </label>
        </div>
        <textarea
          className="input mono"
          name="patterns"
          rows={Math.min(8, Math.max(3, rule.patterns.length))}
          defaultValue={rule.patterns.join("\n")}
          aria-label="Patterns, one per line"
        />
        <div className="rule-actions">
          <button className="btn" type="submit">Save</button>
        </div>
      </form>
      <form action={deleteRuleAction}>
        <input type="hidden" name="id" value={rule.id} />
        <button className="btn-ghost danger" type="submit">Delete</button>
      </form>
    </div>
  );
}

export default async function RulesPage() {
  const configured = isSupabaseConfigured();
  if (configured) {
    try {
      await ensureRulesSeeded();
    } catch {
      /* ignore; page still renders */
    }
  }
  const rules = configured ? await getAllTopicRules() : [];
  const byKind = (k: TopicRuleRow["kind"]) => rules.filter((r) => r.kind === k);

  return (
    <section>
      <h1>Topic rules</h1>
      <p className="muted">
        Edit what WonderBox will answer. One pattern per line — each is a small
        text pattern (regular expression) matched against the question. When in
        doubt, WonderBox defers to you.
      </p>

      {!configured && (
        <p className="alert">
          Supabase isn&apos;t configured yet, so rules can&apos;t be edited here.
          Until then, the built-in defaults are used.
        </p>
      )}

      {configured &&
        (["allow", "deny", "refuse"] as const).map((kind) => (
          <div key={kind} className="rule-group">
            <h2>{KIND_TITLE[kind]}</h2>
            <p className="muted">{KIND_HELP[kind]}</p>
            <div className="rule-grid">
              {byKind(kind).map((r) => (
                <RuleCard key={r.id} rule={r} />
              ))}
            </div>

            <details className="add">
              <summary>+ Add a {kind} topic</summary>
              <form action={addRuleAction} className="rule-form">
                <input type="hidden" name="kind" value={kind} />
                <input className="input" name="rule_key" placeholder="short id, e.g. weather" required />
                <input className="input" name="label" placeholder="label, e.g. weather" required />
                <textarea className="input mono" name="patterns" rows={3} placeholder="one pattern per line" />
                <button className="btn" type="submit">Add</button>
              </form>
            </details>
          </div>
        ))}
    </section>
  );
}
