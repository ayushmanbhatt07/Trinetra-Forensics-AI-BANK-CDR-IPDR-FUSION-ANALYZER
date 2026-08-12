"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Lock, User as UserIcon, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { toast } from "sonner";

export default function LoginPage() {
  const { user, ready, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username || !password) return;
    setBusy(true);
    try {
      await login(username, password);
      toast.success(`Welcome, ${username}`);
      router.replace("/dashboard");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Cannot reach the server. Is the backend running?";
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      <div
        className="absolute inset-0 opacity-40 pointer-events-none"
        style={{
          background:
            "radial-gradient(600px 400px at 80% 20%, rgba(16,185,129,0.12), transparent), radial-gradient(500px 300px at 15% 85%, rgba(34,211,238,0.08), transparent)",
        }}
      />
      <div className="relative w-full max-w-sm mx-4">
        <div className="flex items-center justify-center gap-3 mb-8">
          <Link
            href="/"
            title="Tri-Netra Forensics home"
            aria-label="Tri-Netra Forensics home"
            className="transition-transform duration-200 hover:scale-105"
          >
            <Image
              src="/logo.jpg"
              alt="Tri-Netra Forensics"
              width={44}
              height={44}
              className="w-11 h-11 rounded-xl border border-cyan-500/30 object-cover shadow-lg shadow-cyan-950/40 ring-1 ring-cyan-500/20"
            />
          </Link>
          <div>
            <h1 className="font-mono font-bold tracking-widest text-lg text-emerald-500">
              TRI-NETRA FORENSICS</h1>
            <p className="text-xs text-muted-foreground">AI-Powered Financial & Telecom Dataset Analyzer</p>
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card/80 backdrop-blur-sm shadow-2xl p-8">
          <h2 className="text-lg font-semibold text-foreground mb-1">Restricted Access</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Authorised investigators only. All activity is logged.
          </p>

          <form onSubmit={submit} className="space-y-4">
            {error && (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}
            <div className="relative">
              <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                autoComplete="username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full h-10 pl-9 pr-3 rounded-lg bg-secondary border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-accent"
              />
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="password"
                autoComplete="current-password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-10 pl-9 pr-3 rounded-lg bg-secondary border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-accent"
              />
            </div>
            <button
              type="submit"
              disabled={busy || !username || !password}
              className="w-full h-10 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black font-semibold text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              {busy ? "Authenticating..." : "Sign In"}
            </button>
          </form>

          <p className="text-sm text-muted-foreground text-center mt-6">
            No account yet?{" "}
            <Link href="/signup" className="text-emerald-500 hover:text-emerald-400 font-medium">
              Register
            </Link>
          </p>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6 font-mono">
          FOR AUTHORISED LAW-ENFORCEMENT USE ONLY
        </p>
      </div>
    </main>
  );
}
