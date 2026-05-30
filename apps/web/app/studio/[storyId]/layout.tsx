"use client";
import Link from "next/link";
import { useRouter, useParams, usePathname } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Home, Wand2, FileText, Users, Globe, Network, ShieldCheck, Settings, Map as MapIcon, ListTree, Layers, MapPin, ScrollText, Download, Calendar, Radar, ArrowLeftCircle, Cpu, AlertTriangle } from "lucide-react";
import * as api from "@/lib/api";
import { isAuthed } from "@/lib/auth";
import { useUI, ViewMode } from "@/lib/store";
import { cn } from "@/lib/cn";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

const FLOW_TABS = [
  { href: "flow", icon: Wand2, label: "Flow Writing" },
  { href: "chapters", icon: FileText, label: "Chapters" },
  { href: "characters", icon: Users, label: "Characters" },
  { href: "world", icon: Globe, label: "Your World" },
  { href: "map", icon: Network, label: "Story Map" },
  { href: "check", icon: ShieldCheck, label: "Story Check" },
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
  ]},
  { stage: "Review", pages: [
    { href: "check", icon: ShieldCheck, label: "Story Check" },
    { href: "timeline", icon: Calendar, label: "Timeline" },
    { href: "radar", icon: Radar, label: "Continuity Radar" },
  ]},
];

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams<{ storyId: string }>();
  const pathname = usePathname();
  const { viewMode, setViewMode, llmReachable, setLlmReachable } = useUI();

  useEffect(() => { if (!isAuthed()) router.replace("/login"); }, [router]);

  const { data: story } = useQuery({
    queryKey: ["story", params.storyId],
    queryFn: () => api.getStory(params.storyId),
    enabled: !!params.storyId,
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
    refetchInterval: 60_000,
  });

  return (
    <div className="grid grid-cols-[260px_1fr] min-h-screen">
      <aside className="border-r border-ink-border bg-ink-surface flex flex-col overflow-hidden">
        <div className="px-4 py-4 border-b border-ink-border">
          <Link href="/studio" className="text-xs text-ink-text2 hover:text-ink-goldLight inline-flex items-center gap-1.5">
            <ArrowLeftCircle size={14}/> All stories
          </Link>
          <h2 className="text-lg font-display mt-1 truncate">{story?.title || "…"}</h2>
          <p className="text-xs text-ink-text3">{story?.genre || ""}</p>
        </div>

        <div className="px-4 py-3 border-b border-ink-border">
          <div className="grid grid-cols-2 gap-1 bg-ink-surface2 border border-ink-border rounded-md p-1">
            {(["flow", "studio"] as ViewMode[]).map(m => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={cn(
                  "text-xs py-1.5 px-2 rounded uppercase tracking-wider transition-colors",
                  viewMode === m ? "bg-ink-gold text-ink-deep" : "text-ink-text2 hover:text-ink-text",
                )}
              >{m === "flow" ? "Flow view" : "Studio view"}</button>
            ))}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar-thin p-3">
          {viewMode === "flow" ? (
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
                      const href = `/studio/${params.storyId}/${p.href}`;
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
          <Link href="/settings" className="flex items-center gap-2 px-2 py-1.5 text-ink-text2 hover:text-ink-text">
            <Settings size={12}/> Settings
          </Link>
          <ThemeToggle className="w-full justify-start" />
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
      <main className="overflow-y-auto p-6 scrollbar-thin">{children}</main>
    </div>
  );
}
