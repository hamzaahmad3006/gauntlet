import { Link } from "react-router-dom";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { Footer } from "../../../components/Footer";
import { Logo } from "../../../components/Nav";
import { Badge, Panel } from "../../../components/ui";
import { useLanding } from "./useLanding";

const PILLARS = [
  { t: "Acoustic, black-box", d: "Timing comes from the audio the caller actually receives. One process owns both directions on one clock, so no instrumentation of your agent is needed." },
  { t: "Turn-taking instrumented", d: "Barge-in stop time, talk-over, dead air and premature speech are thresholded metrics, not impressions." },
  { t: "Seeded, reproducible chaos", d: "Frame loss, jitter, delay, noise and interruptions are applied from per-stage seeded streams. Same seed, same impairment schedule." },
  { t: "Arithmetic, not opinion", d: "The readiness score is a documented function of measured values against a versioned threshold profile. No model assigns it." },
];

const METRICS = [
  ["Response latency p50/p95/p99", "caller's last voiced sample → agent's first audio"],
  ["Barge-in stop time p95", "interruption onset → agent speech offset (non-yields censored at 2 s)"],
  ["Talk-over / dead air", "simultaneous speech; agent-side silences over 1.5 s"],
  ["Completion / task success", "sessions without faults; goal checklist met with verbatim turn citations"],
  ["Cost per successful session", "rig cost measured; target cost estimated from your declared prices"],
];

export default function Landing() {
  const { signedIn, calibration } = useLanding();
  return (
    <div className="min-h-full">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Logo />
        <Link to={signedIn ? "/dashboard" : "/login"} className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-bg no-underline">
          {signedIn ? "Open dashboard" : "Sign in"}
        </Link>
      </header>
      <main className="mx-auto max-w-6xl px-4">
        <section className="py-14">
          <Badge tone="info">Load, chaos and benchmark tooling for streaming inference</Badge>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
            The infrastructure crash-test rig for real-time voice AI.
          </h1>
          <p className="mt-4 max-w-2xl text-base text-muted">
            GAUNTLET dials your voice agent with synthetic adversarial callers over real media transport, measures latency,
            turn-taking, reliability and cost from the caller's ear under seeded adverse conditions, and returns a
            deterministic readiness score that can fail a pull request.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to={signedIn ? "/dashboard" : "/login"} className="rounded-md bg-accent px-4 py-2 font-semibold text-bg no-underline">
              Run the example suite
            </Link>
            <a href="https://github.com/hamzaahmad3006/gauntlet" className="rounded-md border border-line px-4 py-2 no-underline">View the repository</a>
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((p) => (
            <div key={p.t} className="rounded-lg border border-line bg-panel p-4">
              <div className="font-semibold">{p.t}</div>
              <p className="mt-1.5 text-sm text-muted">{p.d}</p>
            </div>
          ))}
        </section>

        <section className="mt-8 grid gap-4 lg:grid-cols-3">
          <Panel title="The rig's own error bound" className="lg:col-span-1">
            {calibration?.bound_ms != null ? (
              <>
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-bold num">{calibration.bound_ms} ms</span>
                  <EvidenceLabel kind="MEASURED" />
                </div>
                <p className="mt-2 text-sm text-muted">
                  Maximum absolute error over {calibration.n} loopback repetitions ({calibration.delays_ms?.join(", ")} ms delays),
                  commit <span className="mono">{calibration.git_sha?.slice(0, 8)}</span>. {calibration.scope}.
                </p>
                <Link to="/dashboard/calibration" className="mt-2 inline-block text-sm underline">Method and raw results</Link>
              </>
            ) : (
              <p className="text-sm text-muted">No calibration artefact is committed yet — no bound is claimed.</p>
            )}
          </Panel>
          <Panel title="What it measures" className="lg:col-span-2" pad={false}>
            <table className="w-full text-sm">
              <tbody>
                {METRICS.map(([m, d]) => (
                  <tr key={m} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-2 font-medium">{m}</td>
                    <td className="px-4 py-2 text-muted">{d}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </section>

        <section className="mt-8 rounded-lg border border-line bg-panel2 p-4 text-sm text-muted">
          <span className="font-semibold text-fg">Honest scope.</span> Impairment is applied at the application layer to the
          caller's outbound audio only; frame substitution approximates packet loss rather than reproducing it; the error
          bound is a loopback bound; task success is model inference constrained by citations. No hardware acceleration is
          claimed. Every number here is labelled MEASURED, THRESHOLD or TARGET.
        </section>
      </main>
      <Footer />
    </div>
  );
}
