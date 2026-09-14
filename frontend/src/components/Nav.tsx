import { NavLink, useNavigate } from "react-router-dom";
import { signOut } from "../api/auth";
import { useSession } from "./Session";
import { SystemBadge } from "./SystemBadge";

const links = [
  { to: "/dashboard/talk", label: "Talk to agent", icon: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm7 9a7 7 0 0 1-14 0m7 7v3", highlight: true },
  { to: "/dashboard", label: "Targets", end: true, icon: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-6a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0-3a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" },
  { to: "/dashboard/runs", label: "Runs", icon: "M5 3l14 9-14 9V3Z" },
  { to: "/dashboard/suites", label: "Suites", icon: "M4 6h16M4 12h16M4 18h10" },
  { to: "/dashboard/compare", label: "Compare", icon: "M8 3v18M16 3v18M3 8h5M16 16h5" },
  { to: "/dashboard/ci", label: "CI gate", icon: "M9 12l2 2 4-4M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" },
  { to: "/dashboard/calibration", label: "Calibration", icon: "M3 12h4l3-8 4 16 3-8h4" },
];

export function Logo({ size = "md" }: { size?: "md" | "lg" }) {
  const box = size === "lg" ? "h-9 w-9" : "h-7 w-7";
  return (
    <span className="flex items-center gap-2.5 font-bold tracking-tight">
      <span className={`bg-gradient-brand relative grid ${box} place-items-center rounded-lg shadow-md shadow-cyan-500/30`}>
        <svg viewBox="0 0 32 32" className="h-[70%] w-[70%]" aria-hidden>
          <path d="M4 17h4l3-9 4 15 3-10 2 4h8" stroke="#fff" strokeWidth="2.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className={size === "lg" ? "text-lg" : ""}>GAUNTLET</span>
    </span>
  );
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export function Nav() {
  const nav = useNavigate();
  const { adopt } = useSession();
  return (
    <header className="sticky top-0 z-20 border-b border-white/60 bg-white/70 shadow-[0_1px_0_rgb(15_23_42/0.04)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <NavLink to="/" className="no-underline"><Logo /></NavLink>
        <nav className="order-last -mx-1 flex w-full gap-1 overflow-x-auto px-1 pb-0.5 lg:order-none lg:mx-0 lg:w-auto lg:flex-1 lg:px-0 lg:pb-0">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}
              className={({ isActive }) => `group relative flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium no-underline transition ${
                isActive
                  ? l.highlight ? "btn-glow" : "bg-slate-900 text-white shadow-sm"
                  : l.highlight ? "text-live ring-1 ring-live/30 hover:bg-live/10" : "text-muted hover:bg-panel2 hover:text-fg"}`}>
              <Icon d={l.icon} />
              {l.label}
            </NavLink>
          ))}
        </nav>
        <span className="ml-auto hidden sm:inline-flex lg:ml-0"><SystemBadge /></span>
        <button className="ml-auto rounded-lg px-2 py-1 text-xs text-muted transition hover:bg-panel2 hover:text-fg sm:ml-0" onClick={async () => { await signOut(); adopt(null); nav("/"); }}>
          Sign out
        </button>
      </div>
    </header>
  );
}
