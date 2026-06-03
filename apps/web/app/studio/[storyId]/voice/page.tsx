"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Drama, Fingerprint, MapPin, Ear, GitCompare, Sparkles } from "lucide-react";
import * as api from "@/lib/api";
import { PageHdr, Tag } from "@/components/ui/Primitives";
import { IdentityPanel } from "./_components/IdentityPanel";
import { PlacePanel } from "./_components/PlacePanel";
import { ObserverPanel } from "./_components/ObserverPanel";
import { ComparePanel } from "./_components/ComparePanel";
import { EvolvePanel } from "./_components/EvolvePanel";

type Tab = "identity" | "place" | "observer" | "evolve" | "compare";

const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: "identity", label: "Identity", icon: Fingerprint },
  { key: "place", label: "Place", icon: MapPin },
  { key: "observer", label: "Observer", icon: Ear },
  { key: "evolve", label: "Evolve", icon: Sparkles },
  { key: "compare", label: "Compare", icon: GitCompare },
];

const TAB_KEYS: Tab[] = ["identity", "place", "observer", "evolve", "compare"];

export default function VoiceStudioPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // The active sub-tab is driven by ?tab= so the Voice-view sidebar controls it.
  const urlTab = searchParams.get("tab");
  const tab: Tab = (TAB_KEYS.includes(urlTab as Tab) ? urlTab : "identity") as Tab;
  const setTab = (t: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", t);
    router.push(`${pathname}?${params.toString()}`);
  };

  const { data: characters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });
  const [activeId, setActiveId] = useState<string | null>(null);

  // Deep-link from the Characters tab: /voice?character=<id>
  useEffect(() => {
    const fromUrl = searchParams.get("character");
    if (fromUrl) setActiveId(fromUrl);
  }, [searchParams]);
  useEffect(() => { if (!activeId && characters && characters.length > 0) setActiveId(characters[0].id); }, [characters, activeId]);

  const cast = characters || [];
  const showCharList = tab === "identity";

  return (
    <div>
      <PageHdr
        title="◈ Character Voice Studio"
        subtitle="How the story feels on the page — voice, behavior, atmosphere, fidelity."
        right={<Tag color="gold">Narrative Fidelity Engine</Tag>}
      />

      {/* Sub-tabs */}
      <div className="flex gap-1 mb-5 border-b border-ink-border overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 -mb-px transition-colors shrink-0 whitespace-nowrap ${tab === t.key ? "border-ink-gold text-ink-goldLight" : "border-transparent text-ink-text2 hover:text-ink-text"}`}>
              <Icon size={14}/> {t.label}
            </button>
          );
        })}
      </div>

      <div className={showCharList ? "grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4 lg:gap-6" : ""}>
        {showCharList && (
          <aside>
            <p className="label mb-2 flex items-center gap-1.5"><Drama size={12}/> Cast</p>
            <ul className="space-y-1">
              {cast.map((c: any) => (
                <li key={c.id}>
                  <button onClick={() => setActiveId(c.id)} className={`w-full text-left px-3 py-2 rounded text-sm ${activeId === c.id ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"}`}>
                    {c.name} <span className="text-ink-text3 text-xs">{c.role}</span>
                  </button>
                </li>
              ))}
              {cast.length === 0 && <li className="text-sm text-ink-text3">No characters yet. Add them in the Characters tab.</li>}
            </ul>
          </aside>
        )}

        <section>
          {tab === "identity" && <IdentityPanel storyId={storyId} characters={cast} activeId={activeId} />}
          {tab === "place" && <PlacePanel storyId={storyId} />}
          {tab === "observer" && <ObserverPanel storyId={storyId} />}
          {tab === "evolve" && <EvolvePanel storyId={storyId} />}
          {tab === "compare" && <ComparePanel storyId={storyId} characters={cast} />}
        </section>
      </div>
    </div>
  );
}
