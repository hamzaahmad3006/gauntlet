import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const styles: Record<Variant, string> = {
  primary: "bg-accent text-bg hover:opacity-90 font-semibold",
  secondary: "bg-panel2 text-fg border border-line hover:border-muted",
  danger: "bg-transparent text-breach border border-breach/60 hover:bg-breach/10",
  ghost: "bg-transparent text-muted hover:text-fg",
};

export function Button({ variant = "secondary", children, className = "", busy, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode; busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm transition disabled:opacity-50 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
    >
      {busy && <span className="h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
