/**
 * Warm, kid-friendly canned messages. These are the ONLY thing a child hears
 * when we defer or refuse — no substantive answer ever accompanies them.
 */

const DEFER_MESSAGES = [
  "Ooh, that's a really good question! That's a great one to ask your mom or dad.",
  "What a thoughtful question! I think that's a perfect one for Mom or Dad to answer.",
  "That's a big, wonderful question. Let's save that one for a grown-up you love!",
];

export function deferMessage(seed?: string): string {
  const i = seed ? Math.abs(hash(seed)) % DEFER_MESSAGES.length : Math.floor(Math.random() * DEFER_MESSAGES.length);
  return DEFER_MESSAGES[i];
}

export function refuseMessage(): string {
  // For rule-change / jailbreak attempts: same warm, non-negotiable deferral.
  return "That's a question for your mom or dad. Want to ask me about animals, space, or numbers instead?";
}

export function setupMessage(): string {
  return "Hi! My thinking brain isn't connected yet. Ask a grown-up to finish setting me up!";
}

export function troubleMessage(): string {
  return "Oops! I had a little trouble hearing that. Can you try asking me again?";
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}
