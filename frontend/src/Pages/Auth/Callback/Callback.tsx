import { useAuthCallback } from "./useCallback";

export default function Callback() {
  useAuthCallback();
  return <div className="flex min-h-full items-center justify-center text-sm text-muted">Signing you in…</div>;
}
