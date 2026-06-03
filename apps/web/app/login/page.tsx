"use client";

import { SignIn } from "@clerk/nextjs";

export default function LoginPage() {
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
      <SignIn routing="hash" signUpUrl="/signup" fallbackRedirectUrl="/studio" />
    </main>
  );
}
