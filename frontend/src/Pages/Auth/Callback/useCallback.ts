import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../../../components/Session";

/** Supabase stores the session from the redirect URL; once a token exists, continue to the dashboard. */
export function useAuthCallback() {
  const { token, ready, refresh } = useSession();
  const [params] = useSearchParams();
  const nav = useNavigate();
  useEffect(() => {
    if (ready && token) nav(params.get("next") || "/dashboard", { replace: true });
    else if (ready) {
      const t = setTimeout(refresh, 400);
      return () => clearTimeout(t);
    }
  }, [ready, token, nav, params, refresh]);
}
