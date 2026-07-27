/**
 * Swappable "send a message to the parent" layer.
 *
 * Default provider is email via Resend. Switch to SMS later by setting
 * DIGEST_PROVIDER=sms (Twilio) — no change to the digest code. Sending never
 * throws; it returns a small result so the caller can log/skip cleanly.
 */

export type SendResult = { sent: boolean; skipped?: string; error?: string };

export interface OutgoingMessage {
  subject: string;
  text: string;
  html: string;
}

function provider(): "email" | "sms" {
  return (process.env.DIGEST_PROVIDER || "email").toLowerCase() === "sms" ? "sms" : "email";
}

export function isDigestConfigured(): boolean {
  if (provider() === "sms") {
    return !!(
      process.env.TWILIO_ACCOUNT_SID &&
      process.env.TWILIO_AUTH_TOKEN &&
      process.env.TWILIO_FROM &&
      process.env.DIGEST_TO_SMS
    );
  }
  return !!(process.env.RESEND_API_KEY && process.env.DIGEST_TO_EMAIL);
}

export async function sendMessage(msg: OutgoingMessage): Promise<SendResult> {
  if (!isDigestConfigured()) return { sent: false, skipped: "not_configured" };
  try {
    return provider() === "sms" ? await sendViaTwilio(msg) : await sendViaResend(msg);
  } catch (e) {
    console.error("[digest] send failed:", e);
    return { sent: false, error: (e as Error).message };
  }
}

async function sendViaResend(msg: OutgoingMessage): Promise<SendResult> {
  const apiKey = process.env.RESEND_API_KEY!;
  const to = process.env.DIGEST_TO_EMAIL!;
  const from = process.env.DIGEST_FROM_EMAIL || "WonderBox <onboarding@resend.dev>";

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from, to, subject: msg.subject, html: msg.html, text: msg.text }),
  });
  if (!res.ok) return { sent: false, error: `resend_${res.status}: ${await res.text()}` };
  return { sent: true };
}

async function sendViaTwilio(msg: OutgoingMessage): Promise<SendResult> {
  const sid = process.env.TWILIO_ACCOUNT_SID!;
  const token = process.env.TWILIO_AUTH_TOKEN!;
  const from = process.env.TWILIO_FROM!;
  const to = process.env.DIGEST_TO_SMS!;

  const body = new URLSearchParams({ From: from, To: to, Body: `${msg.subject}\n\n${msg.text}`.slice(0, 1500) });
  const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`, {
    method: "POST",
    headers: {
      Authorization: "Basic " + Buffer.from(`${sid}:${token}`).toString("base64"),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });
  if (!res.ok) return { sent: false, error: `twilio_${res.status}: ${await res.text()}` };
  return { sent: true };
}
