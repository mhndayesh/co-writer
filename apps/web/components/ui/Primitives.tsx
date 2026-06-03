"use client";
import { cn } from "@/lib/cn";
import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Btn({ className, variant = "default", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" }) {
  return <button className={cn("btn", variant === "primary" && "btn-primary", variant === "ghost" && "btn-ghost", className)} {...p} />;
}

export function Inp({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("input", className)} {...p} />;
}

export function Ta({ className, rows = 4, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={rows} className={cn("input resize-y", className)} {...p} />;
}

export function Sel({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return <select className={cn("input", className)} {...p}>{children}</select>;
}

export function FG({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="mb-3">
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-xs text-ink-text3 mt-1">{hint}</p>}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("card-ink p-4", className)}>{children}</div>;
}

export function PageHdr({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 border-b border-ink-border pb-4 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-display text-ink-text">{title}</h1>
        {subtitle && <p className="text-sm text-ink-text2 mt-1">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </header>
  );
}

// Shown when a list/data query FAILS — so a failed fetch is no longer
// indistinguishable from "you have no data" (which reads as "your data is gone").
// Pass the query's `error` and `refetch` so the writer can retry in place.
export function QueryError({ error, retry, what = "this" }: { error: unknown; retry?: () => void; what?: string }) {
  const msg = error instanceof Error ? error.message : "Something went wrong loading your data.";
  return (
    <div className="rounded-lg border border-ink-red/40 bg-ink-red/10 px-4 py-3 text-sm text-ink-text2">
      <p className="text-ink-red font-medium">Couldn’t load {what}.</p>
      <p className="mt-0.5 text-ink-text3">{msg}</p>
      <p className="mt-0.5 text-ink-text3">Your work is safe — this is a loading error, not missing data.</p>
      {retry && (
        <Btn variant="ghost" className="mt-2" onClick={() => retry()}>Try again</Btn>
      )}
    </div>
  );
}

export function Tag({ children, color = "gold" }: { children: ReactNode; color?: "gold" | "red" | "green" | "rose" | "muted" }) {
  const map = {
    gold: "border-ink-gold/40 text-ink-goldLight bg-ink-gold/10",
    red: "border-ink-red/40 text-ink-red bg-ink-red/10",
    green: "border-ink-green/40 text-ink-green bg-ink-green/10",
    rose: "border-ink-rose/40 text-ink-rose bg-ink-rose/10",
    muted: "border-ink-border text-ink-text3 bg-transparent",
  } as const;
  return <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 text-xs uppercase tracking-wider rounded border", map[color])}>{children}</span>;
}
