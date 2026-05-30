"use client";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as api from "@/lib/api";
import { Card, FG, PageHdr, Sel, Tag } from "@/components/ui/Primitives";

type Order = "story" | "reading";
type Group = "none" | "pov" | "thread" | "location";

function groupKey(scene: any, group: Group) {
  if (group === "pov") return scene.pov_name || "No POV";
  if (group === "location") return scene.location_name || "No location";
  if (group === "thread") return (scene.plot_thread_names || [])[0] || "No thread";
  return "Timeline";
}

export default function TimelinePage() {
  const { storyId } = useParams<{ storyId: string }>();
  const [order, setOrder] = useState<Order>("story");
  const [group, setGroup] = useState<Group>("none");
  const { data: scenes } = useQuery({ queryKey: ["timeline", storyId, order], queryFn: () => api.listTimeline(storyId, order) });

  const groups = useMemo(() => {
    const map: Record<string, any[]> = {};
    for (const scene of scenes || []) {
      const key = groupKey(scene, group);
      map[key] = [...(map[key] || []), scene];
    }
    return Object.entries(map);
  }, [scenes, group]);

  return (
    <div className="max-w-5xl">
      <PageHdr title="Memory Timeline" subtitle="Scene chronology, story-time anchors, and continuity lanes." />
      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-2">
          <FG label="Order">
            <Sel value={order} onChange={e => setOrder(e.target.value as Order)}>
              <option value="story">Story time</option>
              <option value="reading">Reading order</option>
            </Sel>
          </FG>
          <FG label="Group">
            <Sel value={group} onChange={e => setGroup(e.target.value as Group)}>
              <option value="none">None</option>
              <option value="pov">POV</option>
              <option value="thread">Plot thread</option>
              <option value="location">Location</option>
            </Sel>
          </FG>
        </div>
      </Card>

      {groups.length === 0 && <Card><p className="text-ink-text2">No scene cards yet. Approve a Flow draft or add scenes manually.</p></Card>}
      <div className="space-y-6">
        {groups.map(([name, rows]) => (
          <section key={name}>
            {group !== "none" && <h2 className="font-display text-xl mb-3">{name}</h2>}
            <ol className="relative border-l border-ink-border ml-3 pl-6 space-y-4">
              {rows.map((s: any) => (
                <li key={s.id} className="relative">
                  <span className="absolute -left-[33px] top-2 w-3 h-3 rounded-full bg-ink-gold border border-ink-deep" />
                  <Card>
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="text-xs text-ink-text3">Ch {s.chapter_number ?? "?"} · Scene {s.ordinal || 0}</span>
                      <h3 className="font-display text-lg">{s.title || s.beat || "Untitled scene"}</h3>
                    </div>
                    {s.summary && <p className="text-sm text-ink-text2 mb-2">{s.summary}</p>}
                    <div className="flex flex-wrap gap-1">
                      {s.time_anchor && <Tag color="gold">{s.time_anchor}</Tag>}
                      {s.duration_hint && <Tag color="muted">{s.duration_hint}</Tag>}
                      {s.pov_name && <Tag color="gold">POV: {s.pov_name}</Tag>}
                      {s.location_name && <Tag color="rose">{s.location_name}</Tag>}
                      {(s.plot_thread_names || []).map((t: string) => <Tag key={t} color="green">{t}</Tag>)}
                    </div>
                  </Card>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
