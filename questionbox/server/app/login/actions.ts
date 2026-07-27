"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  checkPassword,
  createSessionToken,
  isDashboardConfigured,
} from "@/lib/auth/session";

export async function loginAction(formData: FormData): Promise<void> {
  if (!isDashboardConfigured()) redirect("/login?error=unconfigured");

  const password = String(formData.get("password") ?? "");
  if (!checkPassword(password)) redirect("/login?error=1");

  const store = await cookies();
  store.set(SESSION_COOKIE, createSessionToken(), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  redirect("/dashboard");
}

export async function logoutAction(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  redirect("/login");
}
