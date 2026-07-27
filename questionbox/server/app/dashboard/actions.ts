"use server";

import { redirect } from "next/navigation";
import { requireSession } from "@/lib/auth/guard";
import { runDigest } from "@/lib/run-digest";
import { todayStr } from "@/lib/dashboard-data";
import { isDigestConfigured } from "@/lib/email";

/** Manually build & send today's digest so you can test it without waiting for cron. */
export async function sendDigestNowAction(): Promise<void> {
  await requireSession();
  if (!isDigestConfigured()) redirect("/dashboard?digest=unconfigured");

  const result = await runDigest(todayStr(), /* force */ true);
  redirect(`/dashboard?digest=${result.send.sent ? "sent" : "error"}`);
}
