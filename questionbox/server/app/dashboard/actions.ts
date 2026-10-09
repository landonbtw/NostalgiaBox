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
  if (result.send.sent) redirect("/dashboard?digest=sent");
  // Surface the actual failure reason (e.g. the Resend API error) so it's clear
  // what to fix, instead of a generic "check your settings".
  const reason = result.send.error ?? result.send.skipped ?? "unknown";
  redirect(`/dashboard?digest=error&reason=${encodeURIComponent(reason)}`);
}
