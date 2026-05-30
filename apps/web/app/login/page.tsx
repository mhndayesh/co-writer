"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp } from "@/components/ui/Primitives";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      await api.login(email, password);
      router.push("/studio");
    } catch (e: any) {
      setErr(e?.message || "Sign-in failed");
    } finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <p className="text-[10px] uppercase tracking-[0.25em] text-ink-gold mb-3">Co-Writer · G-Ink Studio</p>
        <h1 className="text-2xl font-display mb-1">Welcome back</h1>
        <p className="text-sm text-ink-text2 mb-6">Sign in to your stories.</p>
        <form onSubmit={submit}>
          <FG label="Email"><Inp type="email" required value={email} onChange={e => setEmail(e.target.value)} /></FG>
          <FG label="Password"><Inp type="password" required value={password} onChange={e => setPassword(e.target.value)} /></FG>
          {err && <p className="text-sm text-ink-red mb-3">{err}</p>}
          <Btn type="submit" variant="primary" disabled={busy} className="w-full mt-2">{busy ? "Signing in…" : "Sign in"}</Btn>
        </form>
        <p className="text-sm text-ink-text2 mt-6 text-center">New here? <Link href="/signup" className="text-ink-goldLight">Create an account</Link></p>
      </Card>
    </main>
  );
}
