import { redirect } from "next/navigation";
import { loginAction } from "./actions";
import { hasSession } from "@/lib/auth/guard";
import { isDashboardConfigured } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  if (await hasSession()) redirect("/dashboard");
  const { error } = await searchParams;
  const configured = isDashboardConfigured();

  return (
    <main className="wrap">
      <form className="card" action={loginAction}>
        <div className="logo" aria-hidden>
          <span className="eye" />
          <span className="eye" />
          <span className="mouth" />
        </div>
        <h1>WonderBox</h1>
        <p className="muted">Parent dashboard — please sign in.</p>

        {!configured && (
          <p className="alert">
            Set <code>DASHBOARD_PASSWORD</code> in your environment to enable the
            dashboard.
          </p>
        )}
        {error === "1" && <p className="alert">Incorrect password. Try again.</p>}

        <input
          className="input"
          type="password"
          name="password"
          placeholder="Password"
          autoComplete="current-password"
          required
          disabled={!configured}
        />
        <button className="btn" type="submit" disabled={!configured}>
          Sign in
        </button>
      </form>
    </main>
  );
}
