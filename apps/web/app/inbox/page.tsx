"use client";

import { useRequireAuth } from "@/lib/auth";
import WriterInbox from "@/components/inbox/WriterInbox";

export default function InboxPage() {
  useRequireAuth();

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <WriterInbox />
    </div>
  );
}
