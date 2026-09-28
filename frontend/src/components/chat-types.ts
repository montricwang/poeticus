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
