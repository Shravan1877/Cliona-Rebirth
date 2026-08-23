"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";
import { ConversationSidebar } from "@/components/conversation-sidebar";
import { ChatPane } from "@/components/cliona-chat";
import { loadConversations } from "@/lib/conversations-store";

export const Assistant = () => {
  const { user, isLoaded } = useUser();
  const userId = user?.id;

  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  // Bumped after every exchange so the sidebar re-reads localStorage — see
  // lib/conversations-store.ts for why this is local, not a real fetch.
  const [, setRefreshTick] = useState(0);

  if (!isLoaded || !userId) {
    return <div className="grid h-dvh place-items-center text-muted-foreground">Loading…</div>;
  }

  const conversations = loadConversations(userId);

  return (
    <div className="flex h-dvh">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelect={setActiveConversationId}
        onNewConversation={() => setActiveConversationId(null)}
      />
      <main className="min-w-0 flex-1">
        <ChatPane
          key={activeConversationId ?? "new"}
          userId={userId}
          conversationId={activeConversationId}
          onConversationCreated={(id) => {
            setActiveConversationId(id);
            setRefreshTick((t) => t + 1);
          }}
          onExchangeComplete={() => setRefreshTick((t) => t + 1)}
        />
      </main>
    </div>
  );
};
