import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const styles: Record<Variant, string> = {
  primary: "btn-glow font-semibold",
  secondary: "bg-white text-fg border border-line shadow-sm hover:border-accent/50 hover:shadow",
  danger: "bg-breach/10 text-breach border border-breach/50 hover:bg-breach/20",
  ghost: "bg-transparent text-muted hover:text-fg hover:bg-panel2",
};

export function Button({ variant = "secondary", children, className = "", busy, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode; busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-1.5 text-sm transition duration-150 active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
    >
      {busy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
}
