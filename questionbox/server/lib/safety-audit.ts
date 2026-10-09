/**
 * Content-safety audit — an automated second look at what actually got answered.
 *
 * Every day this re-runs the deterministic safety rules over the interactions
 * that were ANSWERED, and flags any whose question OR answer trips a deny/refuse
 * rule. In a correctly working system this should always be empty (the live
 * pipeline blocks those before answering); a non-empty result means something
 * slipped through and a grown-up should review it. Pure + testable (no network).
 */
import { containsBlockedContent } from "./safety/classifier";
import { DEFAULT_RULES, type SafetyRules } from "./safety/rules";
import type { Interaction } from "./dashboard-data";

export interface AuditFlag {
  id: string;
  created_at: string;
  question: string;
  answer: string;
  where: "question" | "answer" | "both";
  category?: string;
}

/** Flag any ANSWERED interaction whose question or answer trips a block rule. */
export function auditInteractions(
  rows: Interaction[],
  rules: SafetyRules = DEFAULT_RULES,
): AuditFlag[] {
  const flags: AuditFlag[] = [];
  for (const r of rows) {
    if (r.mode !== "answered") continue; // deferred/refused never carry a real answer
    if (r.is_spelling) continue; // spelling is deterministic + safe by construction
    const q = (r.question ?? "").trim();
    const a = (r.answer ?? "").trim();
    const qBad = q ? containsBlockedContent(q, rules) : false;
    const aBad = a ? containsBlockedContent(a, rules) : false;
    if (qBad || aBad) {
      flags.push({
        id: r.id,
        created_at: r.created_at,
        question: q,
        answer: a,
        where: qBad && aBad ? "both" : qBad ? "question" : "answer",
        category: r.category ?? undefined,
      });
    }
  }
  return flags;
}

export interface AuditReport {
  subject: string;
  text: string;
  html: string;
  count: number;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Build the parent-facing alert (only emailed when there are flags). */
export function buildAuditReport(date: string, flags: AuditFlag[], reviewed: number): AuditReport {
  const count = flags.length;
  const subject =
    count === 0
      ? `WonderBox safety check — all clear (${date})`
      : `WonderBox safety check — ${count} item${count === 1 ? "" : "s"} to review (${date})`;

  const lines: string[] = [];
  if (count === 0) {
    lines.push(`Safety check for ${date}: reviewed ${reviewed} answered question${reviewed === 1 ? "" : "s"}, nothing to flag. ✅`);
  } else {
    lines.push(
      `Safety check for ${date}: ${count} answered item${count === 1 ? "" : "s"} tripped a safety rule and should be reviewed.`,
      "",
    );
    for (const f of flags) {
      lines.push(`• Q: ${f.question}`);
      if (f.answer) lines.push(`  A: ${f.answer}`);
      lines.push(`  (flagged in: ${f.where}${f.category ? `, category ${f.category}` : ""})`, "");
    }
    lines.push("Open your dashboard to review and, if needed, tighten the topic rules.");
  }
  const text = lines.join("\n");

  const items = flags
    .map(
      (f) => `
      <li style="margin:10px 0;">
        <div><b>Q:</b> ${escapeHtml(f.question)}</div>
        ${f.answer ? `<div><b>A:</b> ${escapeHtml(f.answer)}</div>` : ""}
        <div style="color:#8a8fa3;font-size:12px;">flagged in ${escapeHtml(f.where)}${f.category ? ` · ${escapeHtml(f.category)}` : ""}</div>
      </li>`,
    )
    .join("");

  const html = `
  <div style="font-family:ui-rounded,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#3a3f58;max-width:560px;margin:0 auto;">
    <div style="background:${count === 0 ? "#eafaf0" : "#fdecec"};border-radius:20px;padding:24px;">
      <h1 style="font-size:20px;margin:0 0 6px;">WonderBox safety check</h1>
      <p style="color:#8a8fa3;margin:0 0 16px;">${escapeHtml(date)}</p>
      ${
        count === 0
          ? `<p>Reviewed <b>${reviewed}</b> answered question${reviewed === 1 ? "" : "s"} — nothing to flag. ✅</p>`
          : `<p><b style="color:#c0392b;">${count}</b> answered item${count === 1 ? "" : "s"} tripped a safety rule and should be reviewed:</p>
             <ul style="padding-left:18px;">${items}</ul>`
      }
    </div>
    <p style="font-size:12px;color:#8a8fa3;text-align:center;margin-top:14px;">Automated safety audit • question &amp; answer text only, never audio</p>
  </div>`;

  return { subject, text, html, count };
}
