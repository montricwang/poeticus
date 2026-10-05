import { createConversationId, loadLastActivePoemId, loadPoemConversation } from "@/lib/chat-storage";

const UUID_PATTERN = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

export function loadInitialChatState() {
  const lastId = loadLastActivePoemId();
  // 当前作品使用 UUID；其他历史值不做猜测或自动映射。
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
