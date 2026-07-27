import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE, verifySessionToken } from "./session";

/** Returns true if the current request has a valid dashboard session. */
export async function hasSession(): Promise<boolean> {
  const store = await cookies();
  return verifySessionToken(store.get(SESSION_COOKIE)?.value);
}

/** Use at the top of any dashboard page / action. Redirects to /login if not authed. */
export async function requireSession(): Promise<void> {
  if (!(await hasSession())) redirect("/login");
}
