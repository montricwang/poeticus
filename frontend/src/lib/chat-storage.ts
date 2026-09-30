import type { ChatTurn } from "@/components/chat-types";
import type { SelectedText } from "@/components/poem-reader";

const STORAGE_KEY = "poeticus:chat-state";
const SCHEMA_VERSION = 1;
const INTERRUPTED_ERROR = "上次生成因页面刷新而中断，请重新请求。";

type StoredTurn = {
  id: number;
  question: string;
  selection: SelectedText | null;
  answer: string | null;
  status: ChatTurn["status"];
  error: string | null;
};

type StoredDraft = {
  question: string;
  selection: SelectedText | null;
};

type StoredConversation = {
  conversationId: string;
  poemId: string;
  turns: StoredTurn[];
  draft: StoredDraft;
  updatedAt: string;
};

type ChatStoreV1 = {
  schemaVersion: 1;
  lastActivePoemId: string | null;
  conversationsByPoem: Record<string, StoredConversation>;
};

export type ConversationSnapshot = {
  conversationId: string;
  poemId: string;
  turns: ChatTurn[];
  draft: StoredDraft;
  updatedAt: string;
};

export type ConversationToSave = {
  conversationId: string;
  poemId: string;
  turns: ChatTurn[];
  draft: StoredDraft;
};

function emptyStore(): ChatStoreV1 {
  return {
    schemaVersion: SCHEMA_VERSION,
    lastActivePoemId: null,
    conversationsByPoem: {},
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSelectedText(value: unknown): value is SelectedText {
  if (!isRecord(value)) return false;

  return (
    typeof value.text === "string" &&
    typeof value.start === "number" &&
    Number.isInteger(value.start) &&
    typeof value.end === "number" &&
    Number.isInteger(value.end)
  );
}

function isNullableSelection(value: unknown): value is SelectedText | null {
  return value === null || isSelectedText(value);
}

function isStoredTurn(value: unknown): value is StoredTurn {
  if (!isRecord(value)) return false;

  return (
    typeof value.id === "number" &&
    Number.isInteger(value.id) &&
    typeof value.question === "string" &&
    isNullableSelection(value.selection) &&
    (typeof value.answer === "string" || value.answer === null) &&
    (value.status === "pending" ||
      value.status === "streaming" ||
      value.status === "done" ||
      value.status === "failed") &&
    (typeof value.error === "string" || value.error === null)
  );
}

function isStoredDraft(value: unknown): value is StoredDraft {
  if (!isRecord(value)) return false;

  return (
    typeof value.question === "string" &&
    isNullableSelection(value.selection)
  );
}

function isStoredConversation(
  value: unknown,
): value is StoredConversation {
  if (!isRecord(value)) return false;

  return (
    typeof value.conversationId === "string" &&
    value.conversationId.length > 0 &&
    typeof value.poemId === "string" &&
    value.poemId.length > 0 &&
    Array.isArray(value.turns) &&
    value.turns.every(isStoredTurn) &&
    isStoredDraft(value.draft) &&
    typeof value.updatedAt === "string"
  );
}

function isChatStoreV1(value: unknown): value is ChatStoreV1 {
  if (!isRecord(value)) return false;
  if (value.schemaVersion !== SCHEMA_VERSION) return false;
  if (
    value.lastActivePoemId !== null &&
    typeof value.lastActivePoemId !== "string"
  ) {
    return false;
  }

  if (!isRecord(value.conversationsByPoem)) return false;

  return Object.entries(value.conversationsByPoem).every(
    ([poemId, conversation]) =>
      isStoredConversation(conversation) && conversation.poemId === poemId,
  );
}

function readStore(): ChatStoreV1 {
  if (typeof window === "undefined") return emptyStore();

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyStore();

    const parsed: unknown = JSON.parse(raw);
    return isChatStoreV1(parsed) ? parsed : emptyStore();
  } catch {
    return emptyStore();
  }
}

function writeStore(store: ChatStoreV1): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // localStorage 可能被禁用、配额耗尽或处于受限环境。
    // 持久化失败不应影响当前页面继续聊天。
  }
}

function restoreTurn(turn: StoredTurn): ChatTurn {
  if (turn.status === "pending" || turn.status === "streaming") {
    return {
      ...turn,
      status: "failed",
      error: INTERRUPTED_ERROR,
      regenerating: false,
      regenerateError: null,
      streamDraft: null,
    };
  }

  return {
    ...turn,
    regenerating: false,
    regenerateError: null,
    streamDraft: null,
  };
}

function storeTurn(turn: ChatTurn): StoredTurn {
  return {
    id: turn.id,
    question: turn.question,
    selection: turn.selection,
    answer: turn.answer,
    status: turn.status,
    error: turn.error,
  };
}

export function createConversationId(): string {
  return window.crypto.randomUUID();
}

export function loadLastActivePoemId(): string | null {
  return readStore().lastActivePoemId;
}

export function saveLastActivePoemId(poemId: string): void {
  const store = readStore();
  store.lastActivePoemId = poemId;
  writeStore(store);
}

export function loadPoemConversation(
  poemId: string,
): ConversationSnapshot | null {
  const stored = readStore().conversationsByPoem[poemId];
  if (!stored) return null;

  return {
    conversationId: stored.conversationId,
    poemId: stored.poemId,
    turns: stored.turns.map(restoreTurn),
    draft: {
      question: stored.draft.question,
      selection: stored.draft.selection,
    },
    updatedAt: stored.updatedAt,
  };
}

export function savePoemConversation(
  conversation: ConversationToSave,
): void {
  const store = readStore();

  store.conversationsByPoem[conversation.poemId] = {
    conversationId: conversation.conversationId,
    poemId: conversation.poemId,
    turns: conversation.turns.map(storeTurn),
    draft: {
      question: conversation.draft.question,
      selection: conversation.draft.selection,
    },
    updatedAt: new Date().toISOString(),
  };

  writeStore(store);
}
