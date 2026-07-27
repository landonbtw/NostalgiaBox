import { getInteractionsByDay } from "./dashboard-data";
import { buildDigest } from "./digest";
import { sendMessage, type SendResult } from "./email";

/** Yesterday's date (UTC) as YYYY-MM-DD — the day a morning digest summarizes. */
export function yesterdayStr(now = new Date()): string {
  const d = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}

export interface RunDigestResult {
  date: string;
  total: number;
  send: SendResult;
}

/**
 * Builds and sends the digest for `date`. When there are no questions and
 * `force` is false, it skips sending (no empty emails).
 */
export async function runDigest(date: string, force = false): Promise<RunDigestResult> {
  const rows = await getInteractionsByDay(date);
  const digest = buildDigest(date, rows, process.env.DIGEST_CHILD_NAME);

  if (digest.total === 0 && !force) {
    return { date, total: 0, send: { sent: false, skipped: "no_questions" } };
  }
  const send = await sendMessage({ subject: digest.subject, text: digest.text, html: digest.html });
  return { date, total: digest.total, send };
}
