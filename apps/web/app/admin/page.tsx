"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api";
import { useEntitlement } from "@/lib/useEntitlement";
import { ActAsControl } from "@/components/billing/ActAsControl";

const PERIODS: { label: string; days: number | null }[] = [
  { label: "1 month", days: 30 },
  { label: "3 months", days: 90 },
  { label: "6 months", days: 180 },
  { label: "1 year", days: 365 },
  { label: "Lifetime", days: null },
];

function durationLabel(days: number | null): string {
  if (days === null || days === undefined) return "Lifetime";
  return PERIODS.find(p => p.days === days)?.label ?? `${days} days`;
}

const css = {
  page: {
    minHeight: "100vh",
    background: "var(--bg)",
    padding: "clamp(24px, 5vw, 56px) clamp(16px, 6vw, 44px)",
    fontFamily: "var(--font-sans)",
  } as React.CSSProperties,
  inner: { maxWidth: 820, margin: "0 auto" } as React.CSSProperties,
  h1: {
    fontSize: "clamp(22px, 3.5vw, 30px)", fontWeight: 700,
    color: "var(--text)", margin: "0 0 6px",
    fontFamily: "var(--font-serif)",
  } as React.CSSProperties,
  sub: { fontSize: 14, color: "var(--muted)", margin: "0 0 36px" } as React.CSSProperties,
  card: {
    background: "var(--surface)", border: "1px solid var(--border)",
    borderRadius: 12, padding: "24px 28px", marginBottom: 20,
  } as React.CSSProperties,
  label: { fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", color: "var(--muted)", textTransform: "uppercase" as const, marginBottom: 8, display: "block" },
  h2: { fontSize: 16, fontWeight: 700, color: "var(--text)", margin: "0 0 18px" } as React.CSSProperties,
  row: { display: "flex", gap: 8, flexWrap: "wrap" as const, alignItems: "center" },
  input: {
    flex: 1, minWidth: 200,
    padding: "9px 12px", borderRadius: 8,
    border: "1px solid var(--border)", background: "var(--bg)",
    color: "var(--text)", fontFamily: "var(--font-sans)", fontSize: 14,
    outline: "none",
  } as React.CSSProperties,
  select: {
    padding: "9px 12px", borderRadius: 8,
    border: "1px solid var(--border)", background: "var(--bg)",
    color: "var(--text)", fontFamily: "var(--font-sans)", fontSize: 14,
  } as React.CSSProperties,
  btn: (accent = false) => ({
    padding: "9px 18px", borderRadius: 8, border: "none", cursor: "pointer",
    fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 700,
    background: accent ? "var(--accent)" : "var(--surface-raised)",
    color: accent ? "var(--accent-text)" : "var(--text)",
    transition: "filter 0.15s",
  } as React.CSSProperties),
  kv: { display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" } as React.CSSProperties,
  key: { fontSize: 13, color: "var(--muted)" } as React.CSSProperties,
  val: { fontSize: 13, fontWeight: 600, color: "var(--text)" } as React.CSSProperties,
  badge: (tier: string) => ({
    display: "inline-block", padding: "2px 10px", borderRadius: 99,
    fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const,
    background: tier === "owner" || tier === "dev_ai" ? "color-mix(in oklab, var(--accent) 18%, transparent)" : "var(--surface-raised)",
    color: tier === "owner" || tier === "dev_ai" ? "var(--accent)" : "var(--muted)",
    border: "1px solid color-mix(in oklab, var(--accent) 22%, transparent)",
  }),
  err: { color: "var(--red)", fontSize: 13, marginTop: 8 } as React.CSSProperties,
  ok: { color: "var(--green, #4ade80)", fontSize: 13, marginTop: 8 } as React.CSSProperties,
};

export default function AdminPage() {
  // Owner-ness comes from the backend entitlement (is_admin or ADMIN_EMAILS) —
  // the same source the API enforces — not a hardcoded email. `isRealOwner`
  // stays true even while shape-shifted into another tier for testing.
  const { isRealOwner, isLoading } = useEntitlement();

  const { data: profile } = useQuery({
    queryKey: ["me", "profile"],
    queryFn: () => api.getMyProfile(),
    enabled: isRealOwner,
    staleTime: 60_000,
  });

  if (isLoading) return null;

  if (!isRealOwner) {
    return (
      <div style={css.page}>
        <div style={css.inner}>
          <h1 style={css.h1}>Access denied</h1>
          <p style={css.sub}>This area is restricted to site owners.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={css.page}>
      <div style={css.inner}>
        <h1 style={css.h1}>⚙ Admin panel</h1>
        <p style={css.sub}>Owner-only. Your account has unlimited access to all services.</p>

        <div style={css.card}><ActAsControl /></div>
        <OwnerUsageCard profile={profile} />
        <UserLookupCard />
        <PromoCodesCard />
      </div>
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  padding: "8px 16px", borderRadius: 8, border: "none",
  background: "var(--accent)", color: "var(--accent-text)",
  fontWeight: 700, fontSize: 13, cursor: "pointer",
};

function PromoCodesCard() {
  const qc = useQueryClient();
  const [tier, setTier] = useState<"dev_ai" | "byok">("dev_ai");
  const [days, setDays] = useState<string>("30");   // "lifetime" sentinel
  const [maxUses, setMaxUses] = useState("");
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const { data: codes = [] } = useQuery({ queryKey: ["admin", "codes"], queryFn: api.adminListCodes });

  const create = useMutation({
    mutationFn: () => api.adminCreateCode({
      tier,
      duration_days: days === "lifetime" ? null : Number(days),
      max_uses: maxUses.trim() ? Number(maxUses) : null,
      note: note.trim() || undefined,
      code: code.trim() || null,
    }),
    onSuccess: () => { setCode(""); setNote(""); setMaxUses(""); qc.invalidateQueries({ queryKey: ["admin", "codes"] }); },
    onError: (e: any) => alert(e.message),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => api.adminDeactivateCode(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "codes"] }),
  });

  function copy(c: string) {
    navigator.clipboard?.writeText(c);
    setCopied(c);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div style={css.card}>
      <h2 style={css.h2}>🎟 Promo / gift codes</h2>
      <p style={{ fontSize: 13, color: "var(--muted)", margin: "-10px 0 16px" }}>
        Mint a code that grants a paid tier for a period. Share it; users redeem it in Settings.
      </p>
      <div style={{ display: "grid", gap: 10 }}>
        <div style={css.row}>
          <select style={css.select} value={tier} onChange={e => setTier(e.target.value as "dev_ai" | "byok")}>
            <option value="dev_ai">Plus (dev_ai)</option>
            <option value="byok">Bring Your Own Key (byok)</option>
          </select>
          <select style={css.select} value={days} onChange={e => setDays(e.target.value)}>
            {PERIODS.map(p => <option key={p.label} value={p.days === null ? "lifetime" : String(p.days)}>{p.label}</option>)}
          </select>
          <input style={css.input} placeholder="Max uses (blank = ∞)" value={maxUses}
            onChange={e => setMaxUses(e.target.value.replace(/[^0-9]/g, ""))} />
        </div>
        <div style={css.row}>
          <input style={{ ...css.input, flex: 1 }} placeholder="Custom code (blank = auto-generate)" value={code} onChange={e => setCode(e.target.value)} />
          <input style={{ ...css.input, flex: 1 }} placeholder="Note (e.g. Beta testers)" value={note} onChange={e => setNote(e.target.value)} />
        </div>
        <div>
          <button style={btnPrimary} disabled={create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Generating…" : "Generate code"}
          </button>
        </div>
      </div>

      <div style={{ marginTop: 20, display: "flex", flexDirection: "column" }}>
        {codes.length === 0 && <p style={css.key}>No codes yet.</p>}
        {codes.map((c: any) => (
          <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "10px 0", borderBottom: "1px solid var(--border)", opacity: c.active ? 1 : 0.5 }}>
            <button onClick={() => copy(c.code)} title="Copy code"
              style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
              {c.code}{copied === c.code ? " ✓" : ""}
            </button>
            <span style={css.key}>{c.tier} · {durationLabel(c.duration_days)} · {c.uses}/{c.max_uses ?? "∞"} used</span>
            {c.note && <span style={{ ...css.key, fontStyle: "italic" }}>“{c.note}”</span>}
            <div style={{ flex: 1 }} />
            {c.active
              ? <button onClick={() => deactivate.mutate(c.id)}
                  style={{ fontSize: 12, color: "var(--muted)", background: "none", border: "1px solid var(--border)", borderRadius: 8, padding: "4px 10px", cursor: "pointer" }}>
                  Deactivate
                </button>
              : <span style={css.key}>inactive</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function OwnerUsageCard({ profile }: { profile: any }) {
  const { data: usage } = useQuery({
    queryKey: ["admin", "usage", profile?.id],
    queryFn: () => api.adminGetUserUsage(profile.id),
    enabled: !!profile?.id,
  });

  if (!profile) return null;

  return (
    <div style={css.card}>
      <h2 style={css.h2}>Your account</h2>
      <div style={css.kv}>
        <span style={css.key}>Email</span>
        <span style={css.val}>{profile.email}</span>
      </div>
      <div style={css.kv}>
        <span style={css.key}>Display name</span>
        <span style={css.val}>{profile.display_name}</span>
      </div>
      <div style={css.kv}>
        <span style={css.key}>User ID</span>
        <span style={{ ...css.val, fontFamily: "monospace", fontSize: 12 }}>{profile.id}</span>
      </div>
      <div style={css.kv}>
        <span style={css.key}>Plan</span>
        <span style={css.badge(usage?.effective_tier ?? "owner")}>
          {usage?.effective_tier ?? "owner"} · {usage?.key_source ?? "server"}
        </span>
      </div>
      <div style={css.kv}>
        <span style={css.key}>Metered?</span>
        <span style={css.val}>{usage?.metered ? "yes" : "no — unlimited"}</span>
      </div>
      {usage?.metered && (
        <>
          <div style={css.kv}>
            <span style={css.key}>Actions used / cap</span>
            <span style={css.val}>{usage.usage.actions_used} / {usage.limits.max_actions ?? "∞"}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Tokens used / cap</span>
            <span style={css.val}>{usage.usage.tokens_used.toLocaleString()} / {usage.limits.max_tokens?.toLocaleString() ?? "∞"}</span>
          </div>
        </>
      )}
    </div>
  );
}

function UserLookupCard() {
  const [userId, setUserId] = useState("");
  const [queried, setQueried] = useState("");
  const [tier, setTier] = useState<"free" | "dev_ai" | "byok">("dev_ai");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: usage, isLoading, error } = useQuery({
    queryKey: ["admin", "usage", queried],
    queryFn: () => api.adminGetUserUsage(queried),
    enabled: !!queried,
    retry: false,
  });

  const setPlan = useMutation({
    mutationFn: () => api.adminSetUserPlan(queried, tier, "active"),
    onSuccess: (res) => setMsg({ ok: true, text: `Plan set to ${res.user?.plan_tier ?? tier}` }),
    onError: (e: any) => setMsg({ ok: false, text: e.message }),
  });

  return (
    <div style={css.card}>
      <h2 style={css.h2}>Look up any user</h2>

      <div style={css.row}>
        <input
          style={css.input}
          placeholder="User ID (from their profile URL or DB)"
          value={userId}
          onChange={e => setUserId(e.target.value)}
          onKeyDown={e => e.key === "Enter" && setQueried(userId.trim())}
        />
        <button style={css.btn(true)} onClick={() => { setQueried(userId.trim()); setMsg(null); }}>
          Look up
        </button>
      </div>

      {isLoading && <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 12 }}>Loading…</p>}
      {error && <p style={css.err}>User not found or access denied.</p>}

      {usage && (
        <div style={{ marginTop: 18 }}>
          <div style={css.kv}>
            <span style={css.key}>Plan tier</span>
            <span style={css.badge(usage.effective_tier)}>{usage.effective_tier}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Plan status</span>
            <span style={css.val}>{usage.plan_status}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Key source</span>
            <span style={css.val}>{usage.key_source}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Metered?</span>
            <span style={css.val}>{usage.metered ? "yes" : "no"}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Actions used</span>
            <span style={css.val}>{usage.usage.actions_used}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Tokens used</span>
            <span style={css.val}>{usage.usage.tokens_used.toLocaleString()}</span>
          </div>
          <div style={css.kv}>
            <span style={css.key}>Cap — actions / tokens</span>
            <span style={css.val}>
              {usage.limits.max_actions ?? "∞"} / {usage.limits.max_tokens?.toLocaleString() ?? "∞"}
            </span>
          </div>

          <div style={{ marginTop: 20 }}>
            <span style={css.label}>Set plan</span>
            <div style={css.row}>
              <select style={css.select} value={tier} onChange={e => setTier(e.target.value as any)}>
                <option value="free">free</option>
                <option value="dev_ai">dev_ai (house-key AI)</option>
                <option value="byok">byok (bring own key)</option>
              </select>
              <button
                style={css.btn(true)}
                onClick={() => { setMsg(null); setPlan.mutate(); }}
                disabled={setPlan.isPending}
              >
                {setPlan.isPending ? "Saving…" : "Apply plan"}
              </button>
            </div>
            {msg && <p style={msg.ok ? css.ok : css.err}>{msg.text}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
