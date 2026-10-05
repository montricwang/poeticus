import { useEffect, useRef } from "react";

import type { ChatTurn } from "@/components/chat-types";
import type { SelectedText } from "@/components/poem-reader";
import { saveLastActivePoemId, savePoemConversation } from "@/lib/chat-storage";

type PersistenceOptions = {
  poemId: string | null;
  readyPoemId: string | null;
  conversationId: string;
  turns: ChatTurn[];
  question: string;
  selected: SelectedText | null;
};

export function useConversationPersistence({
  poemId,
  readyPoemId,
  conversationId,
  turns,
  question,
  selected,
}: PersistenceOptions) {
  const persistenceRef = useRef({
    conversationId,
    poemId,
    readyPoemId: readyPoemId,
    turns,
    question,
    selected,
  });

  useEffect(() => {
    persistenceRef.current = {
      conversationId,
      poemId,
      readyPoemId: readyPoemId,
      turns,
      question,
      selected,
    };
  }, [readyPoemId, conversationId, poemId, question, selected, turns]);

  // 本地存储只是 v0.1 的 persistence adapter。
  // 轻微延迟可避免流式 token 到达时同步写 localStorage 过于频繁。
  useEffect(() => {
    if (!poemId || readyPoemId !== poemId) return;
    const timer = window.setTimeout(() => {
      saveLastActivePoemId(poemId);
      savePoemConversation({
        conversationId,
        poemId,
        turns,
        draft: {
          question,
          selection: selected,
        },
      });
    }, 200);

    return () => window.clearTimeout(timer);
  }, [readyPoemId, conversationId, poemId, question, selected, turns]);

  // 刷新/关闭页面时，把尚未等到定时写入的最新状态再保存一次。
  useEffect(() => {
    function handlePageHide() {
      const current = persistenceRef.current;
      if (!current.poemId || current.readyPoemId !== current.poemId) return;
      saveLastActivePoemId(current.poemId);
      savePoemConversation({
        conversationId: current.conversationId,
        poemId: current.poemId,
        turns: current.turns,
        draft: {
          question: current.question,
          selection: current.selected,
        },
      });
    }

    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, []);

  function persistCurrentConversation() {
    if (!poemId || readyPoemId !== poemId) return;
    saveLastActivePoemId(poemId);
    savePoemConversation({
      conversationId,
      poemId,
      turns,
      draft: {
        question,
        selection: selected,
      },
    });
  }

  return { persistCurrentConversation };
}
