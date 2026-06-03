"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Wand2, FileText, Users, Globe, Network, ShieldCheck, Settings, ListTree, Layers, MapPin, ScrollText, Download, Calendar, Radar, ArrowLeftCircle, Cpu, AlertTriangle, Send, Inbox, BookOpen, Drama, Fingerprint, Ear, Sparkles, GitCompare, Menu, X } from "lucide-react";
import { useAuth } from "@clerk/nextjs";
import * as api from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { useUI, ViewMode } from "@/lib/store";
import { cn } from "@/lib/cn";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { UsageMeter } from "@/components/billing/UsageMeter";
import { TokenCounter } from "@/components/billing/TokenCounter";

const FLOW_TABS = [
  { href: "flow", icon: Wand2, label: "Flow Writing" },
  { href: "chapters", icon: FileText, label: "Chapters" },
  { href: "characters", icon: Users, label: "Characters" },
  { href: "world", icon: Globe, label: "Your World" },
  { href: "map", icon: Network, label: "Story Map" },
  { href: "check", icon: ShieldCheck, label: "Story Check" },
];

// Voice Studio is its own view (third toggle). Its sidebar links route to the
// single /voice page and drive its sub-tab via the ?tab= query param.
const VOICE_SECTIONS: Array<{ stage: string; pages: Array<{ tab: string; icon: any; label: string }> }> = [
  { stage: "Build", pages: [
    { tab: "identity", icon: Fingerprint, label: "Identity" },
    { tab: "place", icon: MapPin, label: "Place" },
  ]},
  { stage: "Write", pages: [
    { tab: "observer", icon: Ear, label: "Observer" },
    { tab: "evolve", icon: Sparkles, label: "Evolve" },
    { tab: "compare", icon: GitCompare, label: "Compare" },
  ]},
];

const STUDIO_STAGES: Array<{ stage: string; pages: Array<{ href: string; icon: any; label: string }> }> = [
  { stage: "Foundation", pages: [
    { href: "world", icon: Globe, label: "World" },
    { href: "board", icon: Layers, label: "Plot Board" },
  ]},
  { stage: "Characters", pages: [
    { href: "characters", icon: Users, label: "Cast" },
    { href: "locations", icon: MapPin, label: "Locations" },
    { href: "factions", icon: Users, label: "Factions" },
  ]},
  { stage: "Plot", pages: [
    { href: "scenes", icon: ListTree, label: "Scene Cards" },
    { href: "threads", icon: ListTree, label: "Plot Threads" },
  ]},
  { stage: "Write", pages: [
    { href: "flow", icon: Wand2, label: "Flow" },
    { href: "chapters", icon: FileText, label: "Chapters" },
  ]},
  { stage: "Produce", pages: [
    { href: "script", icon: ScrollText, label: "Script" },
    { href: "export", icon: Download, label: "Export" },
    { href: "publish", icon: Send, label: "Publish" },
  ]},
  { stage: "Review", pages: [
    { href: "check", icon: ShieldCheck, label: "Story Check" },
    { href: "timeline", icon: Calendar, label: "Timeline" },
    { href: "radar", icon: Radar, label: "Continuity Radar" },
  ]},
];

// Which tabs live in only ONE view. Deep-linking / refreshing a view-exclusive
// tab must flip the sidebar to the matching view, or you get the wrong sidebar
// group with no link back to the page you're on. Tabs shared by both views keep
// whatever toggle the user had (both sidebars can navigate to them anyway).
const _FLOW_HREFS = new Set(FLOW_TABS.map(t => t.href));
const _STUDIO_HREFS = new Set(STUDIO_STAGES.flatMap(s => s.pages.map(p => p.href)));
const STUDIO_ONLY_TABS = new Set(
  [..._STUDIO_HREFS].filter(h => !_FLOW_HREFS.has(h) && h !== "publish"), // publish routes outside /studio
);
const FLOW_ONLY_TABS = new Set([..._FLOW_HREFS].filter(h => !_STUDIO_HREFS.has(h)));

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ storyId: string }>();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { viewMode, setViewMode, llmReachable, setLlmReachable } = useUI();

  useRequireAuth();
  // Gate data fetching on Clerk being hydrated: until `isLoaded`, getToken()
  // can't mint a bearer token, so any query fired now would 401 and only recover
  // on refetch. We hold the children (and our own queries) until then.
  const { isLoaded } = useAuth();

  // Mobile/tablet sidebar drawer (<lg). On desktop the sidebar is always visible
  // and this state is irrelevant (CSS overrides it). Close on every navigation.
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { setNavOpen(false); }, [pathname, searchParams]);

  // Voice Studio is its own view. Keep the toggle and the route in sync:
  // landing on /voice (e.g. the Characters deep-link) flips the toggle to Voice.
  const onVoice = pathname === `/studio/${params.storyId}/voice`;
  const voiceTab = searchParams.get("tab") || "identity";
  useEffect(() => {
    if (onVoice && viewMode !== "voice") setViewMode("voice");
  }, [onVoice, viewMode, setViewMode]);

  // Keep the Flow/Studio toggle in sync with the route for view-exclusive tabs, so
  // refreshing or deep-linking e.g. /locations (Studio-only) or /map (Flow-only)
  // shows the correct sidebar instead of stranding you in the wrong group.
  const currentTab = pathname.split("/")[3] || "";
  useEffect(() => {
    if (onVoice) return; // /voice is handled by its own effect above
    if (STUDIO_ONLY_TABS.has(currentTab) && viewMode !== "studio") setViewMode("studio");
    else if (FLOW_ONLY_TABS.has(currentTab) && viewMode !== "flow") setViewMode("flow");
  }, [currentTab, onVoice, viewMode, setViewMode]);

  // Switching the toggle TO Voice navigates to the page; switching AWAY from it
  // while on /voice sends you to that view's home tab.
  const switchView = (m: ViewMode) => {
    setViewMode(m);
    if (m === "voice") router.push(`/studio/${params.storyId}/voice`);
    else if (onVoice) router.push(`/studio/${params.storyId}/${m === "flow" ? "flow" : "world"}`);
  };

  const { data: story } = useQuery({
    queryKey: ["story", params.storyId],
    queryFn: () => api.getStory(params.storyId),
    enabled: isLoaded && !!params.storyId,
  });

  useQuery({
    queryKey: ["llm-status"],
    queryFn: async () => {
      try {
        const s = await api.llmStatus();
        setLlmReachable(s.reachable);
        return s;
      } catch { setLlmReachable(false); return null; }
    },
    enabled: isLoaded,
    refetchInterval: 60_000,
  });

  // Hold the shell until Clerk has hydrated so child pages don't fire their own
  // queries before the bearer token exists (avoids the 401-then-200 burst).
  if (!isLoaded) {
    return (
      <div className="min-h-screen grid place-items-center text-ink-text2 text-sm">
        <span className="inline-flex items-center gap-2">
          <Cpu size={14} className="animate-pulse" /> Loading…
        </span>
      </div>
    );
  }

  return (
    <>
      {/* Mobile/tablet top bar with the menu button (hidden on desktop). */}
      <div className="lg:hidden sticky top-0 z-30 flex items-center gap-3 border-b border-ink-border bg-ink-surface/95 backdrop-blur px-3 py-2">
        <button
          onClick={() => setNavOpen(true)}
          aria-label="Open menu"
          className="p-1.5 rounded text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"
        >
          <Menu size={18} />
        </button>
        <span className="font-display truncate">{story?.title || "…"}</span>
      </div>

      {/* Backdrop when the drawer is open (mobile only). */}
      {navOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-deep/55 backdrop-blur-[1px] lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden
        />
      )}

      <div className="lg:grid lg:grid-cols-[260px_1fr] lg:min-h-screen">
      <aside
        className={cn(
          "border-r border-ink-border bg-ink-surface flex flex-col overflow-hidden",
          // Desktop: static 260px grid column. Mobile/tablet: fixed off-canvas drawer.
          "fixed inset-y-0 left-0 z-50 w-[260px] max-w-[85vw] transition-transform duration-200 ease-out",
          "lg:static lg:z-auto lg:w-auto lg:max-w-none lg:transition-none lg:translate-x-0",
          navOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          onClick={() => setNavOpen(false)}
          aria-label="Close menu"
          className="lg:hidden absolute top-3 right-3 p-1 rounded text-ink-text3 hover:text-ink-text z-10"
        >
          <X size={16} />
        </button>
        <div className="px-4 py-4 border-b border-ink-border">
          <Link href="/studio" className="text-xs text-ink-text2 hover:text-ink-goldLight inline-flex items-center gap-1.5">
            <ArrowLeftCircle size={14}/> All stories
          </Link>
          <h2 className="text-lg font-display mt-1 truncate">{story?.title || "…"}</h2>
          <p className="text-xs text-ink-text3">{story?.genre || ""}</p>
        </div>

        <div className="px-4 py-3 border-b border-ink-border">
          <div className="grid grid-cols-3 gap-1 bg-ink-surface2 border border-ink-border rounded-md p-1">
            {([["flow", "Flow"], ["studio", "Studio"], ["voice", "Voice"]] as [ViewMode, string][]).map(([m, label]) => (
              <button
                key={m}
                onClick={() => switchView(m)}
                className={cn(
                  "text-xs py-1.5 px-1 rounded uppercase tracking-wide transition-colors",
                  viewMode === m ? "bg-ink-gold text-ink-deep" : "text-ink-text2 hover:text-ink-text",
                )}
              >{label}</button>
            ))}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar-thin p-3">
          {viewMode === "voice" ? (
            <div className="space-y-4">
              <Link href={`/studio/${params.storyId}/voice`} className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                onVoice ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2",
              )}>
                <Drama size={14}/> Character Voice Studio
              </Link>
              {VOICE_SECTIONS.map(s => (
                <div key={s.stage}>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-ink-text3 px-2 mb-1">{s.stage}</p>
                  <ul className="space-y-0.5">
                    {s.pages.map(p => {
                      const active = onVoice && voiceTab === p.tab;
                      const Icon = p.icon;
                      return (
                        <li key={p.tab}>
                          <Link href={`/studio/${params.storyId}/voice?tab=${p.tab}`} className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded text-sm",
                            active ? "bg-ink-gold/10 text-ink-goldLight" : "text-ink-text2 hover:text-ink-text",
                          )}>
                            <Icon size={12}/> {p.label}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          ) : viewMode === "flow" ? (
            <ul className="space-y-1">
              {FLOW_TABS.map(t => {
                const href = `/studio/${params.storyId}/${t.href}`;
                const active = pathname === href;
                const Icon = t.icon;
                return (
                  <li key={t.href}>
                    <Link href={href} className={cn(
                      "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                      active ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2",
                    )}>
                      <Icon size={14} /> {t.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="space-y-4">
              {STUDIO_STAGES.map(s => (
                <div key={s.stage}>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-ink-text3 px-2 mb-1">{s.stage}</p>
                  <ul className="space-y-0.5">
                    {s.pages.map(p => {
                      const href = p.href === "publish"
                        ? `/publish/${params.storyId}`
                        : `/studio/${params.storyId}/${p.href}`;
                      const active = pathname === href;
                      const Icon = p.icon;
                      return (
                        <li key={p.href}>
                          <Link href={href} className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded text-sm",
                            active ? "bg-ink-gold/10 text-ink-goldLight" : "text-ink-text2 hover:text-ink-text",
                          )}>
                            <Icon size={12}/> {p.label}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </nav>

        <div className="p-3 border-t border-ink-border text-xs space-y-0.5">
          <Link href="/" className="flex items-center gap-2 px-2 py-1.5 text-ink-text2 hover:text-ink-text">
            <BookOpen size={12}/> Browse stories
          </Link>
          <Link href="/inbox" className="flex items-center gap-2 px-2 py-1.5 text-ink-text2 hover:text-ink-text">
            <Inbox size={12}/> Reader inbox
          </Link>
          <Link href="/settings" className="flex items-center gap-2 px-2 py-1.5 text-ink-text2 hover:text-ink-text">
            <Settings size={12}/> Settings
          </Link>
          <ThemeToggle className="w-full justify-start" />
          <div className="border-t border-ink-border my-1" />
          <UsageMeter />
          <TokenCounter />
          <div className="flex items-center gap-2 px-2 py-1.5 text-ink-text3">
            <Cpu size={12}/>
            <span>LLM: </span>
            {llmReachable === null && <span>…</span>}
            {llmReachable === true && <span className="text-ink-green">reachable</span>}
            {llmReachable === false && <span className="text-ink-red inline-flex items-center gap-1"><AlertTriangle size={10}/>unreachable</span>}
          </div>
          <div className="px-2 pt-1 pb-0.5">
            <span className="text-ink-gold uppercase tracking-[0.2em]">Co-Writer</span>
            <span className="text-ink-text3 mx-1">·</span>
            <span className="text-ink-text3 uppercase tracking-[0.15em]">G-Ink Studio</span>
          </div>
        </div>
      </aside>
      <main className="min-w-0 overflow-x-hidden p-4 sm:p-6 scrollbar-thin">{children}</main>
      </div>
    </>
  );
}
