import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EvidenceLabel } from "../../../components/EvidenceLabel";
import { Footer } from "../../../components/Footer";
import { Logo } from "../../../components/Nav";
import { Waveform } from "../../../components/Waveform";
import { useLanding } from "./useLanding";

const REPO = "https://github.com/hamzaahmad3006/gauntlet";

const STEPS = [
  { n: "01", t: "Point it at your agent", d: "A WebSocket PCM endpoint or a LiveKit room. No SDK inside your agent, no instrumentation.", icon: "M13 2 3 14h9l-1 8 10-12h-9l1-8Z" },
  { n: "02", t: "Synthetic callers dial in", d: "AI callers with personas (calm, impatient, elderly, on the move) try to finish a real task by voice.", icon: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.5 2.7.6a2 2 0 0 1 1.7 2Z" },
  { n: "03", t: "Chaos, on a seed", d: "Packet loss, jitter, café noise and interruptions, injected mid-call and reproducible from one seed.", icon: "M2 12h3l3-9 4 18 3-9h7" },
  { n: "04", t: "A score that can fail a PR", d: "Latency, turn-taking, reliability and task success become a deterministic grade and a CI gate.", icon: "M9 12l2 2 4-4m6 2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" },
];

const PILLARS = [
  { t: "Acoustic, black-box", d: "Timing comes from the audio the caller actually receives. One process owns both directions on one clock.", tone: "from-emerald-500 to-teal-500", icon: "M3 12h2l3-7 4 14 3-7h6" },
  { t: "Turn-taking instrumented", d: "Barge-in stop time, talk-over, dead air and premature speech are thresholded metrics, not impressions.", tone: "from-cyan-500 to-sky-500", icon: "M8 10h8M8 14h5M21 12a9 9 0 0 1-13.5 7.8L3 21l1.2-4.5A9 9 0 1 1 21 12Z" },
  { t: "Seeded, reproducible chaos", d: "Frame loss, jitter, delay, noise and interruptions come from per-stage seeded streams. Same seed, same schedule.", tone: "from-violet-500 to-fuchsia-500", icon: "M4 4h16v16H4zM9 9h.01M15 15h.01M15 9h.01M9 15h.01" },
  { t: "Arithmetic, not opinion", d: "The readiness score is a documented function of measured values against a versioned threshold profile.", tone: "from-amber-500 to-orange-500", icon: "M4 19h16M7 16V9m5 7V5m5 11v-4" },
];

const METRICS = [
  ["Response latency p50/p95/p99", "caller's last voiced sample → agent's first audio"],
  ["Barge-in stop time p95", "interruption onset → agent speech offset (non-yields censored at 2 s)"],
  ["Talk-over / dead air", "simultaneous speech; agent-side silences over 1.5 s"],
  ["Completion / task success", "sessions without faults; goal checklist met with verbatim turn citations"],
  ["Cost per successful session", "rig cost measured; target cost estimated from your declared prices"],
];

const DEMO = [
  { who: "agent", text: "Thank you for calling Bella Tavola. How can I help you today?" },
  { who: "caller", text: "Hi, I'd like a table for two this Saturday at 8pm." },
  { who: "agent", text: "Of course. What name should I put the booking under?" },
  { who: "caller", text: "Sara — oh, and one of us is vegetarian." },
  { who: "agent", text: "Noted. Table for two, Saturday 8 p.m., under Sara, one vegetarian." },
];

function Icon({ d, className = "h-5 w-5" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

/** An illustrative call card: the bubbles cycle; the two latency bars are the committed benchmark p95s. */
function HeroCard() {
  const [shown, setShown] = useState(1);
  useEffect(() => {
    const t = setInterval(() => setShown((s) => (s >= DEMO.length ? 1 : s + 1)), 1900);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="relative">
      <div className="bg-gradient-brand blob absolute -inset-6 rounded-[2rem] opacity-20 blur-3xl" aria-hidden />
      <div className="glass relative overflow-clip rounded-3xl p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className="relative flex h-2.5 w-2.5">
              <span className="ping-soft absolute inline-flex h-full w-full rounded-full bg-emerald-400" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            Synthetic call in progress
          </div>
          <span className="rounded-full bg-panel2 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted">illustration</span>
        </div>
        <Waveform bars={46} className="mt-4 h-14" />
        <div className="mt-4 h-56 space-y-2 overflow-hidden">
          {DEMO.slice(0, shown).map((m, i) => (
            <div key={i} className={`float-in flex ${m.who === "caller" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] shadow-sm ${m.who === "caller" ? "rounded-br-md bg-gradient-to-br from-blue-500 to-indigo-500 text-white" : "rounded-bl-md border border-line bg-white"}`}>
                <div className={`mb-0.5 text-[10px] font-semibold uppercase tracking-wider ${m.who === "caller" ? "text-white/70" : "text-emerald-600"}`}>{m.who === "caller" ? "GAUNTLET caller" : "Agent under test"}</div>
                {m.text}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-2xl border border-line bg-white/70 p-3">
          <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
            <span>Response latency p95 · mobile network</span>
            <EvidenceLabel kind="MEASURED" />
          </div>
          {[["Tuned agent", 786, "A", "from-emerald-400 to-teal-500"], ["Slow endpointing", 1640, "C", "from-amber-400 to-rose-500"]].map(([name, ms, g, tone]) => (
            <div key={name as string} className="mb-1.5 flex items-center gap-3 text-xs last:mb-0">
              <span className="w-28 shrink-0 text-muted">{name}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-panel2">
                <div className={`h-full rounded-full bg-gradient-to-r ${tone}`} style={{ width: `${Math.round(((ms as number) / 2000) * 100)}%` }} />
              </div>
              <span className="w-16 text-right font-semibold num">{(ms as number).toLocaleString()} ms</span>
              <span className={`grid h-6 w-6 place-items-center rounded-md text-[11px] font-bold ${g === "A" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{g}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { signedIn, calibration } = useLanding();
  const go = (path: string) => (signedIn ? path : `/login?next=${encodeURIComponent(path)}`);
  return (
    <div className="min-h-full overflow-x-clip">
      <header className="sticky top-0 z-20 border-b border-white/60 bg-white/60 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Logo />
          <nav className="hidden items-center gap-6 text-sm text-muted md:flex">
            <a href="#how" className="no-underline hover:text-fg">How it works</a>
            <a href="#measures" className="no-underline hover:text-fg">What it measures</a>
            <a href={REPO} className="no-underline hover:text-fg">GitHub</a>
          </nav>
          <Link to={signedIn ? "/dashboard" : "/login"} className="btn-glow rounded-lg px-4 py-2 text-sm font-semibold no-underline">
            {signedIn ? "Open dashboard" : "Sign in"}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4">
        <section className="relative grid items-center gap-12 py-16 lg:grid-cols-[1.25fr_1fr] lg:py-24">
          <div className="bg-gradient-brand blob pointer-events-none absolute -left-40 top-10 h-72 w-72 rounded-full opacity-20 blur-3xl" aria-hidden />
          <div className="float-in relative">
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white/80 px-3 py-1 text-xs font-medium text-emerald-700 shadow-sm">
              <span className="relative flex h-2 w-2"><span className="ping-soft absolute h-full w-full rounded-full bg-emerald-400" /><span className="relative h-2 w-2 rounded-full bg-emerald-500" /></span>
              Load, chaos and benchmark tooling for streaming voice
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl xl:text-[3.4rem]">
              The crash-test rig for <span className="text-gradient">real-time voice AI.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
              Voice agents rarely fail by saying the wrong thing. They fail by answering late, talking over callers and
              freezing under load. GAUNTLET dials your agent with synthetic callers, measures every turn from the
              caller&apos;s ear, and returns a score that can fail a pull request.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={go("/dashboard/talk")} className="btn-glow inline-flex items-center gap-2 rounded-xl px-5 py-3 text-base font-semibold no-underline">
                <Icon d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm7 9a7 7 0 0 1-14 0m7 7v3" />
                Talk to the agent
              </Link>
              <Link to={go("/dashboard/runs/new")} className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-5 py-3 text-base font-semibold no-underline shadow-sm transition hover:border-emerald-300 hover:shadow-md">
                <Icon d="M5 3l14 9-14 9V3Z" />
                Run a crash test
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted">
              <span className="flex items-center gap-1.5"><Icon d="M20 6 9 17l-5-5" className="h-4 w-4 text-emerald-500" />No agent instrumentation</span>
              <span className="flex items-center gap-1.5"><Icon d="M20 6 9 17l-5-5" className="h-4 w-4 text-emerald-500" />Deterministic score</span>
              <span className="flex items-center gap-1.5"><Icon d="M20 6 9 17l-5-5" className="h-4 w-4 text-emerald-500" />GitHub Action gate</span>
            </div>
          </div>
          <div className="float-in [animation-delay:.15s]"><HeroCard /></div>
        </section>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { v: calibration?.bound_ms != null ? `${calibration.bound_ms} ms` : "—", l: "rig measurement error", k: "MEASURED", s: `over ${calibration?.n ?? 80} loopback repetitions` },
            { v: "8", l: "concurrent calls sustained", k: "MEASURED", s: "one laptop process, before timing slips" },
            { v: "A vs C", l: "tuned vs slow endpointing", k: "MEASURED", s: "same suite, seed and network" },
            { v: "1,500 ms", l: "p95 latency threshold", k: "THRESHOLD", s: "default profile, versioned" },
          ].map((x, i) => (
            <div key={x.l} className="glass lift float-in rounded-2xl p-5" style={{ animationDelay: `${0.05 * i}s` }}>
              <div className="flex items-start justify-between gap-2">
                <div className="text-3xl font-extrabold tracking-tight num text-gradient">{x.v}</div>
                <EvidenceLabel kind={x.k} />
              </div>
              <div className="mt-1 text-sm font-semibold">{x.l}</div>
              <div className="text-xs text-muted">{x.s}</div>
            </div>
          ))}
        </section>

        <section id="how" className="scroll-mt-20 py-20">
          <div className="text-center">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-live">How it works</div>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">From a WebSocket URL to a red CI check</h2>
          </div>
          <div className="relative mt-12 grid gap-5 md:grid-cols-4">
            <div className="bg-gradient-brand absolute left-[12%] right-[12%] top-7 hidden h-0.5 opacity-40 md:block" aria-hidden />
            {STEPS.map((s, i) => (
              <div key={s.n} className="float-in relative text-center" style={{ animationDelay: `${0.08 * i}s` }}>
                <div className="bg-gradient-brand mx-auto grid h-14 w-14 place-items-center rounded-2xl text-white shadow-lg shadow-cyan-500/25 ring-4 ring-white">
                  <Icon d={s.icon} className="h-6 w-6" />
                </div>
                <div className="mt-4 text-[11px] font-bold tracking-widest text-muted">STEP {s.n}</div>
                <div className="mt-1 font-semibold">{s.t}</div>
                <p className="mx-auto mt-1.5 max-w-[16rem] text-sm text-muted">{s.d}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((p) => (
            <div key={p.t} className="glass lift group rounded-2xl p-5">
              <div className={`grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br ${p.tone} text-white shadow-md transition group-hover:scale-110`}>
                <Icon d={p.icon} />
              </div>
              <div className="mt-4 font-semibold">{p.t}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{p.d}</p>
            </div>
          ))}
        </section>

        <section id="measures" className="mt-16 grid scroll-mt-20 gap-5 lg:grid-cols-3">
          <div className="glass relative overflow-clip rounded-3xl p-6">
            <div className="bg-gradient-brand absolute -right-16 -top-16 h-40 w-40 rounded-full opacity-15 blur-2xl" aria-hidden />
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">The rig&apos;s own error bound</div>
            {calibration?.bound_ms != null ? (
              <>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-5xl font-extrabold tracking-tight num text-gradient">{calibration.bound_ms}</span>
                  <span className="text-xl font-semibold text-muted">ms</span>
                  <EvidenceLabel kind="MEASURED" />
                </div>
                <p className="mt-3 text-sm text-muted">
                  Maximum absolute error over {calibration.n} loopback repetitions ({calibration.delays_ms?.join(", ")} ms delays),
                  commit <span className="mono">{calibration.git_sha?.slice(0, 8)}</span>. {calibration.scope}.
                </p>
                <Link to="/dashboard/calibration" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-live no-underline hover:underline">Method and raw results →</Link>
              </>
            ) : (
              <p className="mt-3 text-sm text-muted">No calibration artefact is committed yet — no bound is claimed.</p>
            )}
          </div>
          <div className="glass overflow-hidden rounded-3xl lg:col-span-2">
            <div className="border-b border-line px-6 py-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">What it measures</div>
            <div className="divide-y divide-line/70">
              {METRICS.map(([m, d]) => (
                <div key={m} className="flex flex-col gap-1 px-6 py-3 transition hover:bg-emerald-50/50 sm:flex-row sm:items-center sm:gap-6">
                  <span className="w-60 shrink-0 text-sm font-semibold">{m}</span>
                  <span className="text-sm text-muted">{d}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-16 overflow-hidden rounded-3xl">
          <div className="bg-gradient-brand relative px-8 py-12 text-white sm:px-12">
            <Waveform bars={60} className="pointer-events-none absolute inset-x-0 bottom-0 h-24 opacity-30" tone="white" />
            <div className="relative flex flex-wrap items-center justify-between gap-6">
              <div>
                <h2 className="text-3xl font-bold tracking-tight">Hear the failure before your customers do.</h2>
                <p className="mt-2 max-w-xl text-white/85">Call the bundled agent yourself, or unleash a suite of synthetic callers on it and watch the score.</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link to={go("/dashboard/talk")} className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-900 no-underline shadow-lg transition hover:scale-[1.03]">🎙 Talk to the agent</Link>
                <a href={REPO} className="rounded-xl border border-white/50 px-5 py-3 font-semibold text-white no-underline transition hover:bg-white/10">View on GitHub</a>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-8 rounded-2xl border border-line bg-white/60 p-5 text-sm text-muted">
          <span className="font-semibold text-fg">Honest scope.</span> Impairment is applied at the application layer to the
          caller&apos;s outbound audio only; frame substitution approximates packet loss rather than reproducing it; the error
          bound is a loopback bound; task success is model inference constrained by citations. No hardware acceleration is
          claimed. Benchmark numbers come from a laptop with the bundled agent. Every number here is labelled MEASURED,
          THRESHOLD or TARGET.
        </section>
      </main>
      <Footer />
    </div>
  );
}
