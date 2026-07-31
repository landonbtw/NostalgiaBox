import { runSafetyAudit } from "@/lib/run-safety-audit";
import { yesterdayStr } from "@/lib/run-digest";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/cron/safety-audit — run daily by Vercel Cron.
 *
 * Re-checks the previous day's ANSWERED questions against the safety rules and
 * emails the parent if anything slipped through. Secured with CRON_SECRET the
 * same way as the digest (fail closed). Pass ?date=YYYY-MM-DD to target a day,
 * and ?force=1 to send even on a clean day.
 */
export async function GET(request: Request): Promise<Response> {
  const secret = process.env.CRON_SECRET;
  if (!secret) return Response.json({ error: "cron_secret_not_set" }, { status: 500 });

  const auth = request.headers.get("authorization");
  if (auth !== `Bearer ${secret}`) return Response.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(request.url);
  const dateParam = url.searchParams.get("date");
  const date = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : yesterdayStr();
  const force = url.searchParams.get("force") === "1";

  const result = await runSafetyAudit(date, force);
  console.log(`[cron] safety-audit ${date}: reviewed=${result.reviewed} flagged=${result.flagged} sent=${result.send.sent}`);
  return Response.json({ ok: true, ...result });
}
