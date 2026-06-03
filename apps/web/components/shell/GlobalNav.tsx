"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, ChevronLeft, Bell } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth, useUser, UserButton } from "@clerk/nextjs";
import * as api from "@/lib/api";
import ThemeSwitcher from "@/components/shell/ThemeSwitcher";
import { useMediaQuery } from "@/lib/useMediaQuery";

/** Logical PARENT route for the back button — navigates up the app's structure
 *  (not browser history), so bouncing between two pages can't create a back loop. */
function parentPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length <= 1) return "/";                 // /studio, /pricing, /inbox, /admin, /settings → hub
  if (parts[0] === "studio" || parts[0] === "publish") return "/studio";  // any story sub-page → stories list
  if (parts[0] === "read") return "/" + parts.slice(0, -1).join("/");     // chapter → story → /read
  if (parts[0] === "u") return "/";                  // a profile → hub
  return "/" + parts.slice(0, -1).join("/");         // default: drop the last segment
}

export default function GlobalNav() {
  const pathname = usePathname();
  const router = useRouter();
  // On narrow phones, drop the wordmark and tighten spacing so the bar fits.
  const compact = useMediaQuery("(max-width: 560px)");
  const { isSignedIn } = useAuth();
  const { user } = useUser();
  const authed = !!isSignedIn;

  // The profile link needs the local user id (not the Clerk id), so resolve it
  // from the backend once signed in. getMyProfile() hits /v1/u/me.
  const { data: profile } = useQuery({
    queryKey: ["me", "profile"],
    queryFn: () => api.getMyProfile(),
    enabled: authed,
    staleTime: 5 * 60 * 1000,
  });
  const myUserId: string | null = profile?.id ?? null;

  // Unread notification count for the bell badge (polled).
  const { data: unread = 0 } = useQuery({
    queryKey: ["nav-unread"],
    queryFn: () => api.getNotificationUnreadCount(),
    enabled: authed,
    refetchInterval: 60_000,
  });

  // Admin check: Clerk has the email in the session — no backend round-trip needed.
  // The ADMIN_EMAILS env var guards the backend; this only controls UI visibility.
  const clerkEmail = user?.primaryEmailAddress?.emailAddress ?? "";
  const isAdmin = clerkEmail === "mhndayesh@gmail.com";

  const isHub     = pathname === "/";
  const isInbox   = pathname === "/inbox";
  const isPricing = pathname === "/pricing";

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 40,
      background: "color-mix(in oklab, var(--bg) 88%, transparent)",
      backdropFilter: "blur(14px)",
      borderBottom: "1px solid var(--border)",
    }}>
      <div style={{
        maxWidth: 1180, margin: "0 auto",
        padding: "0 clamp(12px, 4vw, 44px)",
        height: 56, display: "flex", alignItems: "center", gap: compact ? 10 : 20,
      }}>

        {/* Mobile back button — phones expect one everywhere except the hub. */}
        {compact && !isHub && (
          <button
            onClick={() => router.push(parentPath(pathname))}
            aria-label="Back"
            style={{
              background: "none", border: "none", color: "var(--text)", cursor: "pointer",
              display: "flex", alignItems: "center", padding: 4, marginLeft: -4, flexShrink: 0,
            }}
          >
            <ChevronLeft size={22} strokeWidth={2} />
          </button>
        )}

        {/* Brand */}
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9, textDecoration: "none", flexShrink: 0 }}>
          <InkDrop />
          {!compact && (
            <span style={{
              fontFamily: "var(--font-serif)", fontSize: 20, fontWeight: 600,
              color: "var(--text)", letterSpacing: "-0.01em", lineHeight: 1,
            }}>
              G-Ink Studio
            </span>
          )}
        </Link>

        {/* Nav links — shrink + scroll horizontally on small screens instead of
            overflowing the bar. */}
        <nav style={{
          display: "flex", alignItems: "center", gap: 2,
          minWidth: 0, flexShrink: 1, overflowX: "auto", scrollbarWidth: "none",
        }}>
          <NavLink href="/"        active={isHub}>Hub</NavLink>
          <NavLink href="/pricing" active={isPricing}>Pricing</NavLink>
          {authed ? (
            <>
              <NavLink href="/library" active={pathname.startsWith("/library")}>Library</NavLink>
              <NavLink href="/inbox" active={isInbox}>Inbox</NavLink>
              {myUserId && <NavLink href={`/u/${myUserId}`} active={pathname.startsWith("/u/")}>Profile</NavLink>}
              {isAdmin && (
                <NavLink href="/admin" active={pathname.startsWith("/admin")}>
                  ⚙ Admin
                </NavLink>
              )}
            </>
          ) : (
            <NavLink href="/signup" active={false}>For writers</NavLink>
          )}
        </nav>

        <div style={{ flex: 1 }} />

        {/* Right: switcher + auth */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ThemeSwitcher />

          {authed && (
            <Link href="/library" aria-label="Notifications" style={{
              position: "relative", display: "inline-flex", alignItems: "center",
              padding: 7, borderRadius: 8, color: "var(--muted)", textDecoration: "none",
            }}>
              <Bell size={18} />
              {unread > 0 && (
                <span style={{
                  position: "absolute", top: 2, right: 2, minWidth: 15, height: 15,
                  padding: "0 3px", borderRadius: 8, background: "var(--accent)",
                  color: "var(--accent-text)", fontSize: 9, fontWeight: 700,
                  display: "grid", placeItems: "center", lineHeight: 1,
                }}>
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </Link>
          )}

          {authed ? (
            <>
              <Link href="/studio" style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                padding: "7px 14px", borderRadius: 8, textDecoration: "none",
                background: "var(--accent)", color: "var(--accent-text)",
                fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 700,
                transition: "filter 0.15s",
              }}
                onMouseEnter={e => (e.currentTarget.style.filter = "brightness(1.07)")}
                onMouseLeave={e => (e.currentTarget.style.filter = "none")}
              >
                My Studio <ChevronRight size={13} strokeWidth={2.5} />
              </Link>
              <UserButton />
            </>
          ) : (
            <>
              <Link href="/login" style={{
                padding: "7px 10px", borderRadius: 8, textDecoration: "none",
                fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 500,
                color: "var(--muted)", transition: "color 0.15s",
              }}>
                Sign in
              </Link>
              <Link href="/signup" style={{
                display: "inline-flex", alignItems: "center",
                padding: "7px 14px", borderRadius: 8, textDecoration: "none",
                background: "var(--accent)", color: "var(--accent-text)",
                fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 700,
                transition: "filter 0.15s",
              }}
                onMouseEnter={e => (e.currentTarget.style.filter = "brightness(1.07)")}
                onMouseLeave={e => (e.currentTarget.style.filter = "none")}
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function InkDrop() {
  return (
    <span style={{
      display: "inline-block", width: 15, height: 15,
      background: "var(--accent)",
      borderRadius: "50% 50% 50% 3px",
      transform: "rotate(45deg)", flexShrink: 0,
    }} />
  );
}

function NavLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link href={href} style={{
      display: "inline-flex", alignItems: "center",
      padding: "5px 11px", borderRadius: 7, textDecoration: "none",
      fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 500,
      // Keep full label + don't shrink: the nav scrolls as a whole instead of
      // collapsing each link to a single ellipsized letter ("Hub" → "H…").
      flexShrink: 0, overflow: "visible", textOverflow: "clip",
      transition: "all 0.15s",
      color: active ? "var(--accent)" : "var(--muted)",
      background: active ? "var(--accent-soft)" : "transparent",
      border: active
        ? "1px solid color-mix(in oklab, var(--accent) 28%, transparent)"
        : "1px solid transparent",
    }}>
      {children}
    </Link>
  );
}
