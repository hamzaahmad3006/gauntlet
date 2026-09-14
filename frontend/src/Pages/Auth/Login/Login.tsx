import { Link } from "react-router-dom";
import { Logo } from "../../../components/Nav";
import { Waveform } from "../../../components/Waveform";
import { Button } from "../../../components/ui";
import { useLogin } from "./useLogin";

export default function Login() {
  const { github, dev, error, githubEnabled, devEnabled, guest } = useLogin();
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="bg-gradient-brand relative hidden overflow-hidden p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="blob absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/15 blur-3xl" aria-hidden />
        <Link to="/" className="relative text-white no-underline"><Logo size="lg" /></Link>
        <div className="relative">
          <Waveform bars={40} className="h-28" tone="white" />
          <h2 className="mt-8 text-4xl font-extrabold leading-tight tracking-tight">Every millisecond<br />a caller waits, measured.</h2>
          <p className="mt-3 max-w-md text-white/85">Synthetic callers, seeded network chaos and a deterministic readiness score for real-time voice agents.</p>
        </div>
        <div className="relative text-xs text-white/70">Open source · MIT licensed</div>
      </div>
      <div className="flex items-center justify-center px-4 py-12">
        <div className="glass float-in w-full max-w-sm rounded-3xl p-8">
          <Link to="/" className="no-underline lg:hidden"><Logo /></Link>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">Welcome back</h1>
          <p className="mt-1 text-sm text-muted">A workspace with a bundled synthetic agent and test suite is created on first sign-in.</p>
          <div className="mt-8 space-y-3">
            <Button variant={devEnabled ? "secondary" : "primary"} className="w-full py-2.5" onClick={github} disabled={!githubEnabled}>
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.3 4.6 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5Z" /></svg>
              Continue with GitHub
            </Button>
            {devEnabled && (
              <Button variant="primary" className="w-full py-2.5" onClick={dev}>
                {guest ? "Continue as guest (shared demo workspace)" : "Continue as local developer"} →
              </Button>
            )}
            {!githubEnabled && !devEnabled && <p className="text-xs text-muted">Sign-in is not configured on this deployment.</p>}
            {error && <p className="text-xs text-breach">{error}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
