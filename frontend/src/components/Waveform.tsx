/** Decorative animated voice bars. Heights and delays are fixed per index, so the shape is stable between
 * renders; `active` speeds the motion up and `tone` picks the gradient. Purely visual (aria-hidden). */
export function Waveform({ bars = 32, className = "", active = true, tone = "brand" }:
  { bars?: number; className?: string; active?: boolean; tone?: "brand" | "caller" | "agent" | "muted" | "white" }) {
  const gradient = {
    brand: "from-emerald-400 via-cyan-500 to-violet-500",
    caller: "from-blue-400 to-indigo-500",
    agent: "from-emerald-400 to-teal-500",
    muted: "from-slate-300 to-slate-400",
    white: "from-white/60 to-white",
  }[tone];
  return (
    <div className={`flex items-center justify-center gap-[3px] ${className}`} aria-hidden>
      {Array.from({ length: bars }).map((_, i) => {
        const h = 30 + Math.round(70 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.45)));
        return (
          <span key={i}
            className={`wave-bar w-[3px] rounded-full bg-gradient-to-t ${gradient}`}
            style={{ height: `${h}%`, animationDelay: `${(i % 9) * 0.09}s`, animationDuration: active ? `${0.9 + (i % 5) * 0.12}s` : "3.2s", opacity: active ? 1 : 0.55 }} />
        );
      })}
    </div>
  );
}
