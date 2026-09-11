import { NavLink, useNavigate } from "react-router-dom";
import { signOut } from "../api/auth";
import { useSession } from "./Session";
import { SystemBadge } from "./SystemBadge";

const links = [
  { to: "/dashboard", label: "Targets", end: true },
  { to: "/dashboard/runs", label: "Runs" },
  { to: "/dashboard/suites", label: "Suites" },
  { to: "/dashboard/compare", label: "Compare" },
  { to: "/dashboard/ci", label: "CI gate" },
  { to: "/dashboard/calibration", label: "Calibration" },
];

export function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
        <rect width="32" height="32" rx="6" fill="currentColor" className="text-panel2" />
        <path d="M6 20h4l3-9 4 14 3-9 2 4h4" stroke="var(--color-accent)" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      GAUNTLET
    </span>
  );
}

export function Nav() {
  const nav = useNavigate();
  const { refresh } = useSession();
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
        <NavLink to="/" className="no-underline"><Logo /></NavLink>
        <nav className="flex flex-1 gap-1 overflow-x-auto">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end}
              className={({ isActive }) => `whitespace-nowrap rounded px-2.5 py-1 text-sm no-underline ${isActive ? "bg-panel2 text-fg" : "text-muted hover:text-fg"}`}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <SystemBadge />
        <button className="text-xs text-muted hover:text-fg" onClick={async () => { await signOut(); refresh(); nav("/"); }}>
          Sign out
        </button>
      </div>
    </header>
  );
}
