/**
 * Mock conversation list, backed by localStorage.
 *
 * GET /v1/conversations and GET /v1/conversations/{id}/messages (CLAUDE.md
 * §12.2/[B9]) are still Phase 11 stubs on the backend — there is nothing to
 * fetch a real list or history from yet. This store stands in for that: it
 * is local to this browser, per-user (keyed by Clerk user id), and will be
 * replaced by real fetches once those routes exist. Nothing here should be
 * read as "the real persistence layer."
 */

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
};

export type StoredConversation = {
  id: string; // backend conversation_id — a conversation only exists here once the backend has assigned one
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: StoredMessage[];
};

const TITLE_MAX_LEN = 50;

/** Mirrors app/api/routes/chat.py's _generate_title — a local echo, not fetched from the backend. */
export function generateTitle(message: string): string {
  const trimmed = message.trim();
  if (trimmed.length <= TITLE_MAX_LEN) return trimmed || "New Conversation";

  let truncated = trimmed.slice(0, TITLE_MAX_LEN);
  const lastSpace = truncated.lastIndexOf(" ");
  if (lastSpace > 0) truncated = truncated.slice(0, lastSpace);
  return truncated.trimEnd() + "…";
}

function storageKey(userId: string): string {
  return `cliona:conversations:${userId}`;
}

export function loadConversations(userId: string): StoredConversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as StoredConversation[];
    return parsed.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

function saveConversations(userId: string, conversations: StoredConversation[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey(userId), JSON.stringify(conversations));
}

export function upsertConversation(
  userId: string,
  conversationId: string,
  update: (existing: StoredConversation | undefined) => StoredConversation,
): StoredConversation[] {
  const all = loadConversations(userId);
  const idx = all.findIndex((c) => c.id === conversationId);
  const next = update(idx >= 0 ? all[idx] : undefined);

  if (idx >= 0) {
    all[idx] = next;
  } else {
    all.unshift(next);
  }
  saveConversations(userId, all);
  return all.sort((a, b) => b.updatedAt - a.updatedAt);
}

export function appendMessages(
  userId: string,
  conversationId: string,
  title: string,
  newMessages: StoredMessage[],
): StoredConversation[] {
  return upsertConversation(userId, conversationId, (existing) => {
    const now = Date.now();
    return {
      id: conversationId,
      title: existing?.title ?? title,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      messages: [...(existing?.messages ?? []), ...newMessages],
    };
  });
}
