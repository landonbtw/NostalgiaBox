import { getInteractionsByDay } from "./dashboard-data";
import { getRules } from "./safety/rules-store";
import { auditInteractions, buildAuditReport } from "./safety-audit";
import { sendMessage, type SendResult } from "./email";

export interface RunAuditResult {
  date: string;
  reviewed: number;
  flagged: number;
  send: SendResult;
}

/**
 * Loads a day's interactions, re-checks the answered ones against the (editable)
 * safety rules, and emails an alert if anything was flagged. By default it stays
 * quiet on a clean day (no "all clear" spam); pass force=true to always send.
 */
export async function runSafetyAudit(date: string, force = false): Promise<RunAuditResult> {
  const rows = await getInteractionsByDay(date);
  const rules = await getRules();
  const flags = auditInteractions(rows, rules);
  const report = buildAuditReport(date, flags, rows.filter((r) => r.mode === "answered").length);

  if (flags.length === 0 && !force) {
    return { date, reviewed: rows.length, flagged: 0, send: { sent: false, skipped: "all_clear" } };
  }
  const send = await sendMessage({ subject: report.subject, text: report.text, html: report.html });
  return { date, reviewed: rows.length, flagged: flags.length, send };
}
