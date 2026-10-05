import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import { fetchPoem, poemText } from "@/data/poem-library";
import type { Poem } from "@/data/poem-library";
import { loadPoemConversation } from "@/lib/chat-storage";
import { validSelectionForPoem } from "@/lib/selection-offset";
import type { SelectedText } from "@/components/poem-reader";

export function usePoemDetail(
  poemId: string | null,
  setSelected: Dispatch<SetStateAction<SelectedText | null>>,
) {
  const [activePoem, setActivePoem] = useState<Poem | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailAttempt, setDetailAttempt] = useState(0);
  const detailLoading = !!poemId && !activePoem && !detailError;

  // 首屏／刷新时恢复 UUID；点击切诗由 handlePoemChange 先预取再提交。
  useEffect(() => {
    if (!poemId || activePoem?.id === poemId) return;
    const controller = new AbortController();

    void fetchPoem(poemId, controller.signal)
      .then((work) => {
        if (controller.signal.aborted) return;
        setActivePoem(work);
        setSelected(
          validSelectionForPoem(
            loadPoemConversation(work.id)?.draft.selection ?? null,
            poemText(work),
          ),
        );
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDetailError(error instanceof Error ? error.message : "无法加载作品");
      })
    return () => controller.abort();
  }, [poemId, activePoem?.id, detailAttempt, setSelected]);

  function retryDetail() {
    setDetailError("");
    setActivePoem(null);
    setSelected(null);
    setDetailAttempt((count) => count + 1);
  }

  return {
    activePoem,
    setActivePoem,
    detailError,
    setDetailError,
    detailLoading,
    retryDetail,
  };
}
