"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// /read redirects to / — the homepage is the discovery hub
export default function ReadRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/"); }, [router]);
  return null;
}
