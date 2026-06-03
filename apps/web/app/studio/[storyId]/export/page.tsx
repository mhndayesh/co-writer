"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Download, FileText, FileJson, FileType } from "lucide-react";
import * as api from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Btn, Card, PageHdr } from "@/components/ui/Primitives";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

export default function ExportPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const [busy, setBusy] = useState("");

  async function downloadBlob(path: string, filename: string) {
    setBusy(filename);
    try {
      const token = await getToken();
      const r = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } finally { setBusy(""); }
  }

  async function downloadBundle() {
    setBusy("bundle");
    try {
      const bundle = await api.exportBundle(storyId);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `story_${storyId}.bundle.json`; document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } finally { setBusy(""); }
  }

  return (
    <div className="max-w-2xl">
      <PageHdr title="Export" subtitle="Pull your story out of the studio." />
      <Card className="mb-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div><h3 className="font-display text-lg"><FileText size={16} className="inline mr-1"/> Markdown</h3><p className="text-sm text-ink-text2">A clean manuscript with chapters, summaries, and cast.</p></div>
          <Btn variant="primary" disabled={busy !== ""} onClick={() => downloadBlob(`/v1/stories/${storyId}/export/markdown`, `story_${storyId}.md`)}><Download size={14}/> {busy === `story_${storyId}.md` ? "…" : "Download"}</Btn>
        </div>
      </Card>
      <Card className="mb-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div><h3 className="font-display text-lg"><FileType size={16} className="inline mr-1"/> DOCX</h3><p className="text-sm text-ink-text2">For Word, Google Docs, beta-reader review.</p></div>
          <Btn variant="primary" disabled={busy !== ""} onClick={() => downloadBlob(`/v1/stories/${storyId}/export/docx`, `story_${storyId}.docx`)}><Download size={14}/> {busy === `story_${storyId}.docx` ? "…" : "Download"}</Btn>
        </div>
      </Card>
      <Card>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div><h3 className="font-display text-lg"><FileJson size={16} className="inline mr-1"/> Backup bundle (JSON)</h3><p className="text-sm text-ink-text2">Story Forge-compatible snapshot. Re-importable.</p></div>
          <Btn variant="primary" disabled={busy !== ""} onClick={downloadBundle}><Download size={14}/> {busy === "bundle" ? "…" : "Download"}</Btn>
        </div>
      </Card>
    </div>
  );
}
