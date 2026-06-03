"use client";

import { Suspense } from "react";
import { SignUp } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";

// Only honour same-origin absolute paths — never a protocol-relative `//evil.com`
// or an external URL — so the post-signup redirect can't be turned into an open
// redirect. Falls back to the studio hub.
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return "/studio";
}

function SignupForm() {
  // pricing → /signup?next=/pricing; carry that intent through so a paid-plan
  // signup lands back where they meant to go instead of always /studio.
  const redirect = safeNext(useSearchParams().get("next"));
  return (
    <SignUp
      routing="hash"
      signInUrl="/login"
      fallbackRedirectUrl={redirect}
      forceRedirectUrl={redirect}
    />
  );
}

export default function SignupPage() {
  return (
    <main
      style={{
        minHeight: "calc(100vh - 56px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "32px 16px",
      }}
    >
      {/* useSearchParams needs a Suspense boundary in the App Router. */}
      <Suspense fallback={null}>
        <SignupForm />
      </Suspense>
    </main>
  );
}
