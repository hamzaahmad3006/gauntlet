import { Link } from "react-router-dom";
import { Logo } from "../../../components/Nav";
import { Button } from "../../../components/ui";
import { useLogin } from "./useLogin";

export default function Login() {
  const { github, dev, error, githubEnabled, devEnabled } = useLogin();
  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-xl border border-line bg-panel p-6">
        <Link to="/" className="no-underline"><Logo /></Link>
        <h1 className="mt-6 text-lg font-semibold">Sign in</h1>
        <p className="mt-1 text-sm text-muted">A workspace with a bundled synthetic agent and suite is created on first sign-in.</p>
        <div className="mt-6 space-y-2">
          <Button variant="primary" className="w-full" onClick={github} disabled={!githubEnabled}>
            Continue with GitHub
          </Button>
          {devEnabled && (
            <Button className="w-full" onClick={dev}>Continue as local developer</Button>
          )}
          {!githubEnabled && !devEnabled && <p className="text-xs text-muted">Sign-in is not configured on this deployment.</p>}
          {error && <p className="text-xs text-breach">{error}</p>}
        </div>
      </div>
    </div>
  );
}
