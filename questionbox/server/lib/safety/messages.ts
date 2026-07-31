/**
 * Warm, kid-friendly canned messages. These are the ONLY thing a child hears
 * when we defer or refuse — no substantive answer ever accompanies them.
 */

const DEFER_MESSAGES = [
  "Ooh, that's a really good question! That's a great one to ask your mom or dad.",
  "What a thoughtful question! I think that's a perfect one for Mom or Dad to answer.",
  "That's a big, wonderful question. Let's save that one for a grown-up you love!",
  "Great question! That's a special one to ask your mom or dad.",
  "Hmm, that one's for a grown-up. Ask your mom or dad — they'll know!",
  "Oooh, that's a tricky one! It's a perfect question for your mom or dad.",
  "I love how curious you are! That's a wonderful one to ask a grown-up you trust.",
  "That's a really important question. Let's ask your mom or dad about that one together!",
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

// Said when speech-to-text couldn't make out the recording. Rotated for variety
// so it doesn't feel robotic when a child has to repeat themselves.
const TROUBLE_MESSAGES = [
  "Sorry, I didn't catch that! Can you say it again?",
  "Oops, I didn't quite hear you. Can you ask me one more time?",
  "Hmm, I missed that one! Could you say it again for me?",
  "Sorry! My ears got a little mixed up. Can you say that again?",
  "I didn't catch that — can you try asking me one more time?",
  "Whoops, that was too quiet for me! Can you say it a bit louder?",
];

export function troubleMessage(): string {
  return TROUBLE_MESSAGES[Math.floor(Math.random() * TROUBLE_MESSAGES.length)];
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}
