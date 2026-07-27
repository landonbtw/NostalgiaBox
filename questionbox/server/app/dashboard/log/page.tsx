import Link from "next/link";
import { getInteractionsByDay, todayStr, type Interaction } from "@/lib/dashboard-data";
import { isSupabaseConfigured } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function shiftDay(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const MODE_LABEL: Record<Interaction["mode"], string> = {
  answered: "Answered",
  deferred: "Sent to grown-up",
  refused: "Declined",
};

export default async function LogPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string; q?: string }>;
}) {
  const { date: dateParam, q } = await searchParams;
  const date = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : todayStr();
  const configured = isSupabaseConfigured();
  const rows = configured ? await getInteractionsByDay(date, q) : [];

  return (
    <section>
      <h1>Question log</h1>

      <form className="filters" method="get">
        <label>
          Day
          <input className="input" type="date" name="date" defaultValue={date} />
        </label>
        <label className="grow">
          Search
          <input className="input" type="search" name="q" placeholder="search questions & answers" defaultValue={q ?? ""} />
        </label>
        <button className="btn" type="submit">Go</button>
      </form>

      <div className="daynav">
        <Link href={`/dashboard/log?date=${shiftDay(date, -1)}`}>← Previous day</Link>
        <span>{date}</span>
        <Link href={`/dashboard/log?date=${shiftDay(date, 1)}`}>Next day →</Link>
      </div>

      {!configured && <p className="alert">Supabase isn&apos;t configured yet.</p>}

      {configured && rows.length === 0 && <p className="muted">No questions{q ? " match your search" : ""} on this day.</p>}

      <ul className="log">
        {rows.map((r) => (
          <li key={r.id} className={`log-item mode-${r.mode}`}>
            <div className="log-top">
              <span className="time">{timeOf(r.created_at)}</span>
              <span className={`badge badge-${r.mode}`}>{MODE_LABEL[r.mode]}</span>
              {r.category && <span className="cat">{r.category}</span>}
              {r.is_spelling && <span className="cat">spelling</span>}
            </div>
            <div className="q">{r.question || <em>(no transcript)</em>}</div>
            <div className="a">{r.answer}</div>
            {r.reason && r.mode !== "answered" && <div className="why">why: {r.reason}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
