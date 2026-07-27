export default function Home() {
  return (
    <main className="wrap">
      <div className="card">
        <div className="logo" aria-hidden>
          <span className="eye" />
          <span className="eye" />
          <span className="mouth" />
        </div>
        <h1>WonderBox</h1>
        <p>
          The friendly brain behind the kids&apos; question box. This server
          receives audio from the device, runs the safety layer, and speaks a
          short, safe answer back.
        </p>
        <p className="muted">
          The parent dashboard arrives in a later stage. If you can read this,
          the server is running.
        </p>
      </div>
    </main>
  );
}
