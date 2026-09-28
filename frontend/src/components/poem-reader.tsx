import { useEffect, useRef } from "react";
import { BookOpen } from "lucide-react";

import { Card } from "@/components/ui/card";
import { poem } from "@/data/sample-poem";

export type SelectedText = {
  text: string;
  start: number;
  end: number;
};

type PoemReaderProps = {
  onSelect: (selection: SelectedText) => void;
};

export function PoemReader({ onSelect }: PoemReaderProps) {
  const readerRef = useRef<HTMLDivElement>(null);
  const poemRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    let pointerDown = false;
    let pointerStartedInReader = false;

    function handleSelection(allowOutsideAnchor = false) {
      const reader = readerRef.current;
      const element = poemRef.current;
      const selection = window.getSelection();

      if (
        !reader ||
        !element ||
        !selection ||
        selection.isCollapsed ||
        selection.rangeCount === 0
      ) {
        return;
      }

      // 键盘选择等情况，仍要求从左侧阅读区域开始。
      // 鼠标操作则使用 pointerdown 记录的起点判断。
      if (
        !allowOutsideAnchor &&
        (!selection.anchorNode || !reader.contains(selection.anchorNode))
      ) {
        return;
      }

      const textNode = element.firstChild;

      if (!textNode || textNode.nodeType !== Node.TEXT_NODE) {
        return;
      }

      const range = selection.getRangeAt(0);

      // 诗歌正文在 DOM 中的范围。
      const poemRange = document.createRange();
      poemRange.selectNodeContents(textNode);

      // 最终选区必须真正包含至少一部分诗歌正文。
      const endsBeforePoem =
        range.compareBoundaryPoints(Range.START_TO_END, poemRange) <= 0;

      const startsAfterPoem =
        range.compareBoundaryPoints(Range.END_TO_START, poemRange) >= 0;

      if (endsBeforePoem || startsAfterPoem) {
        return;
      }

      // 截取选区与诗歌正文的交集。
      // 即使选区包含标题、说明文字，也只引用诗歌。
      const clippedRange = range.cloneRange();

      if (
        clippedRange.compareBoundaryPoints(Range.START_TO_START, poemRange) < 0
      ) {
        clippedRange.setStart(textNode, 0);
      }

      if (clippedRange.compareBoundaryPoints(Range.END_TO_END, poemRange) > 0) {
        clippedRange.setEnd(textNode, textNode.textContent?.length ?? 0);
      }

      const text = clippedRange.toString();

      if (!text.trim()) {
        return;
      }

      // 计算截取后的文字在原始诗歌中的位置。
      const prefixRange = document.createRange();
      prefixRange.selectNodeContents(textNode);
      prefixRange.setEnd(clippedRange.startContainer, clippedRange.startOffset);

      const start = prefixRange.toString().length;
      const end = start + text.length;

      // 保持与 FastAPI 的引用位置校验一致。
      if (poem.slice(start, end) !== text) {
        return;
      }

      onSelect({ text, start, end });
    }

    function handlePointerDown(event: PointerEvent) {
      pointerDown = true;

      pointerStartedInReader =
        event.target instanceof Node &&
        !!readerRef.current?.contains(event.target);
    }

    function handlePointerUp() {
      const startedInReader = pointerStartedInReader;

      pointerDown = false;
      pointerStartedInReader = false;

      // 只有从左侧阅读区域开始的拖选，才更新诗歌引用。
      if (startedInReader) {
        handleSelection(true);
      }
    }

    function handlePointerCancel() {
      pointerDown = false;
      pointerStartedInReader = false;
    }

    function handleSelectionChange() {
      // 拖动期间暂不更新，等待鼠标松开后的最终选区。
      if (!pointerDown) {
        handleSelection();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerCancel);
    document.addEventListener("selectionchange", handleSelectionChange);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerCancel);
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [onSelect]);

  return (
    <Card
      ref={readerRef}
      className="min-h-155 gap-0 overflow-hidden border-border/60 bg-card/90 py-0 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/20"
    >
      <div className="flex items-center justify-between border-b border-border/60 px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-600 dark:text-violet-300">
            <BookOpen className="size-5" />
          </div>

          <div>
            <h2 className="text-sm font-semibold">诗词阅读</h2>

            <p className="text-xs text-muted-foreground">
              在文字之间，发现更多
            </p>
          </div>
        </div>

        <span className="rounded-full border border-border/70 px-3 py-1 text-xs text-muted-foreground">
          阅读模式
        </span>
      </div>

      <article className="mx-auto w-full max-w-xl px-7 py-12 sm:px-12 sm:py-16">
        <header className="mb-12 text-center">
          <div className="mb-5 text-xs tracking-[0.35em] text-muted-foreground">
            CLASSICAL POETRY
          </div>

          <h1 className="font-serif text-4xl font-medium tracking-widest">
            浣溪沙
          </h1>

          <div className="mx-auto mt-7 h-px w-12 bg-violet-400/60" />
        </header>

        <p
          ref={poemRef}
          className="cursor-text select-text whitespace-pre-line font-serif text-lg leading-[3] tracking-wide text-foreground/90 selection:bg-violet-200 selection:text-violet-950 dark:selection:bg-violet-400/40 dark:selection:text-white sm:text-xl"
        >
          {poem}
        </p>

        <div className="mt-16 border-t border-border/60 pt-6 text-center">
          <p className="text-xs leading-6 text-muted-foreground">
            选中任意字词或诗句，即可在右侧引用并提问
          </p>
        </div>
      </article>
    </Card>
  );
}
