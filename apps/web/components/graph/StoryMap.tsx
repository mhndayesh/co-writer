"use client";
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false }) as any;

export type GraphData = {
  nodes: Array<{ id: string; label: string; kind: string; color: string; size: number }>;
  links: Array<{ source: string; target: string; kind: string; label?: string }>;
};

export function StoryMap({ data }: { data: GraphData }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useSize();

  useEffect(() => {
    function onResize() {
      if (!ref.current) return;
      const r = ref.current.getBoundingClientRect();
      setSize({ w: r.width, h: r.height });
    }
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [setSize]);

  return (
    <div ref={ref} className="w-full h-[70vh] bg-ink-surface border border-ink-border rounded">
      <ForceGraph2D
        graphData={data}
        width={size.w}
        height={size.h}
        backgroundColor={cssVar("--ink-bg", "10 8 6")}
        nodeRelSize={4}
        nodeLabel={(n: any) => `${n.label} (${n.kind})`}
        nodeCanvasObject={(node: any, ctx: any, globalScale: number) => {
          const size = (node.size || 4) + 2;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.color || "#c89830";
          ctx.fill();
          ctx.strokeStyle = "rgba(0,0,0,0.4)";
          ctx.lineWidth = 1;
          ctx.stroke();
          const label = node.label || "";
          const fontSize = Math.max(10 / globalScale, 6);
          ctx.font = `${fontSize}px "Playfair Display", serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillStyle = cssVar("--ink-text", "232 220 200");
          ctx.fillText(label, node.x, node.y + size + 2);
        }}
        linkColor={(l: any) => l.kind === "relationship"
          ? `rgb(${cssVar("--ink-gold", "200 152 48", true)} / 0.5)`
          : `rgb(${cssVar("--ink-text", "232 220 200", true)} / 0.18)`}
        linkWidth={(l: any) => l.kind === "relationship" ? 1.4 : 0.8}
        linkLabel={(l: any) => l.label || l.kind}
        d3Force={"charge" as any}
        cooldownTime={2500}
      />
    </div>
  );
}

function useSize(): [{ w: number; h: number }, (s: { w: number; h: number }) => void] {
  const [size, setSize] = useState({ w: 800, h: 600 });
  return [size, setSize];
}

// Read a CSS variable defined in globals.css (e.g. "--ink-bg" → "10 8 6").
// Falls back to the dark-mode default if accessed during SSR.
function cssVar(name: string, fallback: string, raw = false): string {
  if (typeof window === "undefined") return raw ? fallback : `rgb(${fallback})`;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  return raw ? v : `rgb(${v})`;
}
