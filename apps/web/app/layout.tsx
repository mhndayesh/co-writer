import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/shell/Providers";
import { ThemeBoot } from "@/components/shell/ThemeBoot";

export const metadata: Metadata = {
  title: "Co-Writer — by G-Ink Studio",
  description: "Your AI co-writer. Write freely; the craft happens behind the scenes.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeBoot />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
