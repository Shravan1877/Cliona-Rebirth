"use client";

import { UserButton } from "@clerk/nextjs";
import { PenSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StoredConversation } from "@/lib/conversations-store";
import { ThemeToggle } from "@/components/theme-toggle";

type ConversationSidebarProps = {
  conversations: StoredConversation[];
  activeConversationId: string | null;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
};

export function ConversationSidebar({
  conversations,
  activeConversationId,
  onSelect,
  onNewConversation,
}: ConversationSidebarProps) {
  return (
    <aside className="flex h-dvh w-72 shrink-0 flex-col border-r border-border/60 bg-sidebar">
      <div className="flex items-center justify-between gap-2 px-4 pt-5 pb-3">
        <span className="font-mono text-sm font-medium tracking-wide text-foreground/80">
          Cliona
        </span>
        <ThemeToggle />
      </div>

      <div className="px-3">
        <button
          onClick={onNewConversation}
          className="flex w-full items-center gap-2 rounded-2xl border border-border/60 bg-card px-3 py-2.5 text-sm text-foreground shadow-soft transition-colors hover:bg-accent"
        >
          <PenSquare className="size-4 text-primary" />
          New conversation
        </button>
      </div>

      <nav className="mt-3 flex-1 space-y-0.5 overflow-y-auto px-3">
        {conversations.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            No conversations yet. Say something.
          </p>
        )}
        {conversations.map((c) => {
          const isActive = c.id === activeConversationId;
          return (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={cn(
                "block w-full truncate rounded-xl px-3 py-2.5 text-left text-sm transition-colors",
                isActive ? "bg-primary/10 text-foreground" : "text-foreground/75 hover:bg-accent",
              )}
              title={c.title}
            >
              {c.title}
            </button>
          );
        })}
      </nav>

      <div className="space-y-2 border-t border-border/60 px-4 py-3">
        <p className="text-[11px] leading-snug text-muted-foreground">
          This list lives in your browser for now — the backend&apos;s conversation-list endpoint
          isn&apos;t built yet (Phase 11), so nothing here syncs across devices or survives clearing
          site data.
        </p>
        <div className="flex items-center gap-2.5 pt-1">
          <span className="shrink-0">
            <UserButton afterSignOutUrl="/" />
          </span>
          <span className="text-xs text-muted-foreground">Account</span>
        </div>
      </div>
    </aside>
  );
}
