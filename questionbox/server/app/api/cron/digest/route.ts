import { runDigest, yesterdayStr } from "@/lib/run-digest";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/cron/digest — run daily by Vercel Cron.
 *
 * Vercel automatically sends `Authorization: Bearer <CRON_SECRET>` when the
 * CRON_SECRET env var is set; we require it (fail closed) so nobody else can
 * trigger digests. Summarizes the previous day by default; pass ?date=YYYY-MM-DD
 * to target a specific day.
 */
export async function GET(request: Request): Promise<Response> {
  const secret = process.env.CRON_SECRET;
  if (!secret) return Response.json({ error: "cron_secret_not_set" }, { status: 500 });

  const auth = request.headers.get("authorization");
  if (auth !== `Bearer ${secret}`) return Response.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(request.url);
  const dateParam = url.searchParams.get("date");
  const date = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : yesterdayStr();

  const result = await runDigest(date);
  console.log(`[cron] digest ${date}: total=${result.total} sent=${result.send.sent} ${result.send.skipped ?? result.send.error ?? ""}`);
  return Response.json({ ok: true, ...result });
}
