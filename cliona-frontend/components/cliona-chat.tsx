"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import {
  appendMessages,
  generateTitle,
  loadConversations,
  type StoredMessage,
} from "@/lib/conversations-store";
import { sendChatMessage, ChatApiError } from "@/lib/cliona-api";

function toInitialMessages(stored: StoredMessage[]): ThreadMessageLike[] {
  return stored.map((m) => ({
    id: m.id,
    role: m.role,
    content: [{ type: "text" as const, text: m.text }],
    createdAt: new Date(m.createdAt),
  }));
}

function lastUserText(messages: readonly ThreadMessage[]): string {
  const last = messages[messages.length - 1];
  return last.content
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
}

type ChatPaneProps = {
  userId: string;
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
  onExchangeComplete: () => void;
};

/**
 * Remounted (via `key`) whenever the active conversation changes — this is
 * what gives each conversation an isolated useLocalRuntime instance without
 * assistant-ui's cloud-shaped RemoteThreadListAdapter, which assumes a
 * thread can be `initialize()`d before the first message. Our backend does
 * the opposite: it creates the conversation (and its title) as a side
 * effect of the first /v1/chat call, so there is no remoteId to hand the
 * adapter up front.
 */
export function ChatPane({
  userId,
  conversationId,
  onConversationCreated,
  onExchangeComplete,
}: ChatPaneProps) {
  const { getToken } = useAuth();

  const initialMessages = conversationId
    ? toInitialMessages(
        loadConversations(userId).find((c) => c.id === conversationId)?.messages ?? [],
      )
    : [];

  const model: ChatModelAdapter = {
    async run({ messages, abortSignal }) {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const userText = lastUserText(messages);

      try {
        const result = await sendChatMessage(token, userText, conversationId, abortSignal);

        const now = Date.now();
        const userMsg: StoredMessage = {
          id: `u-${now}`,
          role: "user",
          text: userText,
          createdAt: now,
        };
        const assistantMsg: StoredMessage = {
          id: `a-${now}`,
          role: "assistant",
          text: result.response,
          createdAt: now + 1,
        };

        appendMessages(userId, result.conversation_id, generateTitle(userText), [
          userMsg,
          assistantMsg,
        ]);

        if (!conversationId) {
          onConversationCreated(result.conversation_id);
        }
        onExchangeComplete();

        return { content: [{ type: "text", text: result.response }] };
      } catch (err) {
        if (err instanceof ChatApiError) {
          throw new Error(`${err.status}: ${err.message}`);
        }
        throw err;
      }
    },
  };

  const runtime = useLocalRuntime(model, { initialMessages });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}
