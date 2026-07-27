import Link from "next/link";
import { requireSession } from "@/lib/auth/guard";
import { logoutAction } from "@/app/login/actions";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  await requireSession();

  return (
    <div className="dash">
      <header className="dash-header">
        <div className="dash-brand">
          <span className="dot" aria-hidden />
          WonderBox
        </div>
        <nav className="dash-nav">
          <Link href="/dashboard">Summary</Link>
          <Link href="/dashboard/log">Question log</Link>
          <Link href="/dashboard/rules">Topic rules</Link>
        </nav>
        <form action={logoutAction}>
          <button className="btn-ghost" type="submit">Sign out</button>
        </form>
      </header>
      <main className="dash-main">{children}</main>
    </div>
  );
}
