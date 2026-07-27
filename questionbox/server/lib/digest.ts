/**
 * Builds the friendly daily digest from a day's interactions. Pure and
 * testable — no network. The cron route loads the data and hands it here.
 */
import type { Interaction } from "./dashboard-data";

export interface Digest {
  subject: string;
  text: string;
  html: string;
  total: number;
}

function prettyDate(date: string): string {
  const d = new Date(`${date}T12:00:00.000Z`);
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" });
}

function cleanQuestion(q: string): string {
  let s = q.trim().replace(/\s+/g, " ");
  if (s.length > 90) s = s.slice(0, 87) + "…";
  return s;
}

/** Dedupe (case-insensitive) and cap a list of questions. */
function sampleQuestions(rows: Interaction[], max: number): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rows) {
    const q = (r.question ?? "").trim();
    if (!q) continue;
    const key = q.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(cleanQuestion(q));
    if (out.length >= max) break;
  }
  return out;
}

export function buildDigest(date: string, rows: Interaction[], childName?: string): Digest {
  const who = childName && childName.trim() ? childName.trim() : "the kids";
  const answered = rows.filter((r) => r.mode === "answered");
  const deferred = rows.filter((r) => r.mode === "deferred");
  const refused = rows.filter((r) => r.mode === "refused");
  const total = rows.length;

  const examples = sampleQuestions(answered.length ? answered : rows, 5);
  const pretty = prettyDate(date);

  const subject =
    total === 0
      ? `WonderBox — a quiet day (${date})`
      : `WonderBox — ${who} asked ${total} question${total === 1 ? "" : "s"} (${date})`;

  // Plain text
  const lines: string[] = [];
  if (total === 0) {
    lines.push(`No questions for WonderBox on ${pretty}. A quiet day!`);
  } else {
    const intro =
      examples.length > 0
        ? `On ${pretty}, ${who} asked WonderBox about things like:`
        : `On ${pretty}, ${who} asked WonderBox ${total} question${total === 1 ? "" : "s"}.`;
    lines.push(intro, "");
    for (const q of examples) lines.push(`  • ${q}`);
    lines.push("");
    lines.push(
      `WonderBox answered ${answered.length}, gently sent ${deferred.length} to a grown-up` +
        (refused.length ? `, and declined ${refused.length}` : "") + ".",
    );
    lines.push("");
    lines.push("See everything in your dashboard.");
  }
  const text = lines.join("\n");

  // HTML
  const exHtml = examples.map((q) => `<li style="margin:4px 0;">${escapeHtml(q)}</li>`).join("");
  const html = `
  <div style="font-family:ui-rounded,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#3a3f58;max-width:520px;margin:0 auto;">
    <div style="background:#fff3e0;border-radius:20px;padding:24px;">
      <h1 style="font-size:22px;margin:0 0 6px;">WonderBox daily note</h1>
      <p style="color:#8a8fa3;margin:0 0 16px;">${escapeHtml(pretty)}</p>
      ${
        total === 0
          ? `<p>No questions today — a quiet day! 🌙</p>`
          : `<p>${escapeHtml(who === "the kids" ? "The kids" : who)} asked WonderBox about:</p>
             <ul style="padding-left:18px;">${exHtml}</ul>
             <p style="margin-top:16px;">
               <b style="color:#2e9e5b;">${answered.length}</b> answered,
               <b style="color:#d98324;">${deferred.length}</b> sent to a grown-up${
                 refused.length ? `, <b style="color:#c0392b;">${refused.length}</b> declined` : ""
               }.
             </p>`
      }
    </div>
    <p style="font-size:12px;color:#8a8fa3;text-align:center;margin-top:14px;">Sent by your WonderBox • question &amp; answer text only, never audio</p>
  </div>`;

  return { subject, text, html, total };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
