import { createConversationId, loadLastActivePoemId, loadPoemConversation } from "@/lib/chat-storage";

const UUID_PATTERN = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

export function loadInitialChatState() {
  const lastId = loadLastActivePoemId();
  // 旧 demo 作品使用短字符串 ID；保留旧会话，不将其自动映射到 UUID。
  const poemId = lastId && UUID_PATTERN.test(lastId) ? lastId : null;
  const storedConversation = poemId ? loadPoemConversation(poemId) : null;
  const turns = storedConversation?.turns ?? [];

  return {
    poemId,
    conversationId: storedConversation?.conversationId ?? createConversationId(),
    turns,
    question: storedConversation?.draft.question ?? "",
  };
}

export type InitialChatState = ReturnType<typeof loadInitialChatState>;
