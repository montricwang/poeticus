import type { SelectedText } from "@/components/poem-reader";

export type ChatTurn = {
  id: number;
  question: string;
  selection: SelectedText | null;
  answer: string | null;
  status: "pending" | "streaming" | "done" | "failed";
  error: string | null;
  regenerating: boolean;
  regenerateError: string | null;
  /** 重新生成期间保留旧 answer，新版本写到这里。 */
  streamDraft: string | null;
};

export type ChatViewport = {
  scrollTop: number;
  atBottom: boolean;
};
