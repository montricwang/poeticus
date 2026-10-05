import type { ChatTurn, HistoryMessage } from "@/components/chat-types";

function historyUserContent(turn: ChatTurn) {
  if (!turn.selection) {
    return turn.question;
  }

  return `引用原文：${turn.selection.text}\n\n问题：${turn.question}`;
}

export function buildHistory(
  turns: ChatTurn[],
  currentTurnId: number,
  maxHistoryTurns: number,
): HistoryMessage[] {
  if (maxHistoryTurns <= 0) {
    return [];
  }

  const currentIndex = turns.findIndex((turn) => turn.id === currentTurnId);

  // 新发送的 Turn 还没进入当前 render 的 turns，因此找不到时，
  // 当前已有 turns 全部都是它之前的历史。
  const previousTurns =
    currentIndex === -1 ? turns : turns.slice(0, currentIndex);

  const completedTurns = previousTurns
    .filter(
      (turn) =>
        turn.status === "done" &&
        turn.answer !== null &&
        turn.answer.trim() !== "",
    )
    .slice(-maxHistoryTurns);

  return completedTurns.flatMap((turn) => [
    {
      role: "user" as const,
      content: historyUserContent(turn),
    },
    {
      role: "assistant" as const,
      content: turn.answer!.trim(),
    },
  ]);
}
