import type { SelectedText } from "@/components/poem-reader";

export type ChatTurn = {
  id: number;
  question: string;
  selection: SelectedText | null;
  answer: string | null;
  status: "pending" | "done" | "failed";
  error: string | null;
  regenerating: boolean;
  regenerateError: string | null;
};

// 离开聊天视图时仍保留滚动位置与是否在底部的信息。
export type ChatViewport = {
  scrollTop: number;
  atBottom: boolean;
};
