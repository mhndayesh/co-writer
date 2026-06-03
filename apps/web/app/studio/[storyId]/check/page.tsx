"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ShieldCheck, AlertOctagon, AlertTriangle, Info } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, PageHdr, Sel, Tag } from "@/components/ui/Primitives";
import { AiLockNotice } from "@/components/billing/AiLockNotice";
import { useEntitlement } from "@/lib/useEntitlement";

const SEVERITY_TAG: Record<string, any> = { high: { color: "red", icon: AlertOctagon }, medium: { color: "gold", icon: AlertTriangle }, low: { color: "muted", icon: Info } };
const PASSES = [
  ["logic", "Logic / continuity"],
  ["structure", "Structure"],
  ["character", "Character"],
  ["dialogue", "Dialogue"],
  ["tightening", "Tightening"],
];

export default function CheckPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { aiAvailable } = useEntitlement();
  const [chapterId, setChapterId] = useState("");
  const [passType, setPassType] = useState("logic");

  const run = useMutation({
    mutationKey: ["llm", "story-check", passType],
    mutationFn: () => api.storyCheck(storyId, chapterId, passType),
  });

  return (
    <div className="max-w-4xl">
      <PageHdr title="◇ Story Check" subtitle="Reads the chapter against your world, cast, and history — uses Graph-RAG for subtle continuity slips." />

      <AiLockNotice />

      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-[1fr_220px_auto] items-end">
          <FG label="Chapter to check">
            <Sel value={chapterId} onChange={e => setChapterId(e.target.value)}>
              <option value="">— pick a chapter —</option>
              {(chapters || []).map((c: any) => <option key={c.id} value={c.id}>Ch{c.number}. {c.title}</option>)}
            </Sel>
          </FG>
          <FG label="Revision pass">
            <Sel value={passType} onChange={e => setPassType(e.target.value)}>
              {PASSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Sel>
          </FG>
          <Btn variant="primary" disabled={!chapterId || run.isPending || !aiAvailable} onClick={() => run.mutate()} className="mb-3">
            <ShieldCheck size={14}/> {run.isPending ? "Reading…" : "Run check"}
          </Btn>
        </div>
      </Card>

      {run.isError && (
        <Card className="mb-4 border-ink-red/40">
          <p className="text-ink-red text-sm font-medium">Story Check couldn’t run.</p>
          <p className="text-ink-text3 text-sm mt-0.5">
            {run.error instanceof Error ? run.error.message : "Something went wrong."}
          </p>
          <Btn variant="ghost" className="mt-2" onClick={() => run.mutate()}>Try again</Btn>
        </Card>
      )}

      {run.isSuccess && !run.data?.fallback
        && (run.data?.findings || []).length === 0
        && (run.data?.strengths || []).length === 0 && (
        <Card className="mb-4">
          <p className="text-sm text-ink-text2">No issues or notes came back for this pass. Try another revision pass, or check your AI model in Settings if you expected findings.</p>
        </Card>
      )}

      {run.data && (
        <>
          <Card className="mb-4">
            <h3 className="font-display text-lg mb-2">Severity</h3>
            <div className="flex flex-wrap gap-2">
              <Tag color="green">{run.data.pass_type || passType}</Tag>
              <Tag color="red">High · {run.data.severity_buckets?.high ?? 0}</Tag>
              <Tag color="gold">Medium · {run.data.severity_buckets?.medium ?? 0}</Tag>
              <Tag color="muted">Low · {run.data.severity_buckets?.low ?? 0}</Tag>
            </div>
            {run.data.fallback && <p className="text-xs text-ink-text3 mt-2">⚠ Fallback mode — connect LM Studio in Settings for real analysis.</p>}
          </Card>

          {(run.data.findings || []).length > 0 && (
            <Card className="mb-4">
              <h3 className="font-display text-lg mb-3">Findings</h3>
              <ul className="space-y-3">
                {run.data.findings.map((f: any, i: number) => {
                  const cfg = SEVERITY_TAG[f.severity] || SEVERITY_TAG.low;
                  const Icon = cfg.icon;
                  return (
                    <li key={i} className="border-l-2 pl-3" style={{ borderColor: f.severity === "high" ? "#b34535" : f.severity === "medium" ? "#c89830" : "#54473a" }}>
                      <div className="flex items-center gap-2 mb-1">
                        <Icon size={14} />
                        <strong>{f.title}</strong>
                        <Tag color={cfg.color as any}>{f.severity}</Tag>
                      </div>
                      <p className="text-sm text-ink-text2">{f.detail}</p>
                      {f.suggestion && <p className="text-xs text-ink-goldLight mt-1">→ {f.suggestion}</p>}
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}

          {(run.data.strengths || []).length > 0 && (
            <Card>
              <h3 className="font-display text-lg mb-3">What's working</h3>
              <ul className="space-y-1 text-sm">
                {run.data.strengths.map((s: string, i: number) => <li key={i}>✓ {s}</li>)}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
