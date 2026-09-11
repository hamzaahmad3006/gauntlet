// Sign-in: GitHub OAuth through Supabase in production; a local "dev" token when the backend runs in
// development without Supabase. The session token is read by client.ts and attached there only.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const DEV_KEY = "gauntlet.dev-session";
let supabase: SupabaseClient | null = null;

export function configureAuth(url: string, anonKey: string): void {
  if (url && anonKey && !supabase) {
    supabase = createClient(url, anonKey, { auth: { persistSession: true, detectSessionInUrl: true } });
  }
}

export const authAvailable = () => supabase !== null;

export async function currentToken(): Promise<string | null> {
  try {
    if (localStorage.getItem(DEV_KEY) === "1") return "dev";
  } catch {
    /* storage blocked */
  }
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function signInWithGitHub(redirectTo: string): Promise<void> {
  if (!supabase) throw new Error("GitHub sign-in is not configured on this deployment.");
  await supabase.auth.signInWithOAuth({ provider: "github", options: { redirectTo } });
}

export function signInDev(): void {
  try {
    localStorage.setItem(DEV_KEY, "1");
  } catch {
    /* ignore */
  }
}

export async function signOut(): Promise<void> {
  try {
    localStorage.removeItem(DEV_KEY);
  } catch {
    /* ignore */
  }
  if (supabase) await supabase.auth.signOut();
}

export function onAuthChange(cb: () => void): () => void {
  if (!supabase) return () => undefined;
  const { data } = supabase.auth.onAuthStateChange(() => cb());
  return () => data.subscription.unsubscribe();
}
