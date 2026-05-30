"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BusyOverlay } from "@/components/shell/BusyOverlay";

export function Providers({ children }: { children: React.ReactNode }) {
  // staleTime 0 so navigating between tabs always reflects the latest server
  // state (a chapter deleted on the Chapters tab is immediately reflected on
  // Flow). refetchOnWindowFocus still off — only re-fetch on remount.
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { refetchOnWindowFocus: false, staleTime: 0, refetchOnMount: "always" },
    },
  }));
  return (
    <QueryClientProvider client={client}>
      {children}
      <BusyOverlay />
    </QueryClientProvider>
  );
}
