/** Client for the real, non-streaming POST /v1/chat (CLAUDE.md §12.2/§12.3, Phase 6). */

export type ChatResponse = {
  response: string;
  conversation_id: string;
};

export class ChatApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const API_URL = process.env.NEXT_PUBLIC_CLIONA_API_URL ?? "http://localhost:8000";

export async function sendChatMessage(
  token: string,
  message: string,
  conversationId: string | null,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ChatApiError(res.status, body.detail ?? `Request failed (${res.status})`);
  }

  return res.json();
}
