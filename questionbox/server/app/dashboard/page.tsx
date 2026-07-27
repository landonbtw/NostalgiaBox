import Link from "next/link";
import { getDailySummary, todayStr } from "@/lib/dashboard-data";
import { isSupabaseConfigured } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function DashboardHome() {
  const configured = isSupabaseConfigured();
  const today = todayStr();
  const summary = configured ? await getDailySummary(today) : null;

  return (
    <section>
      <h1>Today</h1>

      {!configured && (
        <p className="alert">
          Supabase isn&apos;t configured yet, so there&apos;s nothing to show.
          Add the Supabase environment variables and run <code>supabase/schema.sql</code>.
        </p>
      )}

      {summary && (
        <>
          <p className="lead">{summary.friendly}</p>

          <div className="stats">
            <div className="stat stat-answered">
              <div className="stat-num">{summary.answered}</div>
              <div className="stat-label">Answered</div>
            </div>
            <div className="stat stat-deferred">
              <div className="stat-num">{summary.deferred}</div>
              <div className="stat-label">Sent to a grown-up</div>
            </div>
            <div className="stat stat-refused">
              <div className="stat-num">{summary.refused}</div>
              <div className="stat-label">Declined</div>
            </div>
          </div>

          {summary.topics.length > 0 && (
            <div className="topics">
              <h2>Topics they explored</h2>
              <ul className="chips">
                {summary.topics.map((t) => (
                  <li key={t.label} className="chip">
                    {t.label} <span className="chip-count">{t.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p>
            <Link className="btn" href={`/dashboard/log?date=${today}`}>
              See today&apos;s questions
            </Link>
          </p>
        </>
      )}
    </section>
  );
}
