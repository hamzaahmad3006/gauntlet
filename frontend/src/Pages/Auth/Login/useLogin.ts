import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { authAvailable, signInDev, signInWithGitHub } from "../../../api/auth";
import { useSession } from "../../../components/Session";

export function useLogin() {
  const { system, adopt } = useSession();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const next = params.get("next") || "/dashboard";

  const github = async () => {
    setError(null);
    try {
      await signInWithGitHub(`${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const dev = () => {
    signInDev();
    adopt("dev");
    nav(next);
  };
  return { github, dev, error, githubEnabled: authAvailable() || !!system?.auth.supabase_url,
    devEnabled: !!system?.auth.dev_login, guest: !!system?.auth.guest };
}
