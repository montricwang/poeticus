import { useEffect, useRef } from "react";

import { Card } from "@/components/ui/card";
import { poemText } from "@/data/poem-library";
import type { Poem } from "@/data/poem-library";

export type SelectedText = {
  text: string;
  start: number;
  end: number;
};

type PoemReaderProps = {
  work: Poem;
  onSelect: (selection: SelectedText) => void;
};

export function PoemReader({ work, onSelect }: PoemReaderProps) {
  const poem = poemText(work);
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

      // 正文保留为一个文本节点，标题与词序不参与 offset 计算。
      const textNode = element.firstChild;
      if (!textNode || textNode.nodeType !== Node.TEXT_NODE) {
        return;
      }

      const range = selection.getRangeAt(0);
      const poemRange = document.createRange();
      poemRange.selectNodeContents(textNode);

      const endsBeforePoem =
        range.compareBoundaryPoints(Range.START_TO_END, poemRange) <= 0;
      const startsAfterPoem =
        range.compareBoundaryPoints(Range.END_TO_START, poemRange) >= 0;
      if (endsBeforePoem || startsAfterPoem) {
        return;
      }

      const clippedRange = range.cloneRange();
      if (
        clippedRange.compareBoundaryPoints(Range.START_TO_START, poemRange) < 0
      ) {
        clippedRange.setStart(textNode, 0);
      }
      if (
        clippedRange.compareBoundaryPoints(Range.END_TO_END, poemRange) > 0
      ) {
        clippedRange.setEnd(textNode, textNode.textContent?.length ?? 0);
      }

      const text = clippedRange.toString();
      if (!text.trim()) {
        return;
      }

      const prefixRange = document.createRange();
      prefixRange.selectNodeContents(textNode);
      prefixRange.setEnd(clippedRange.startContainer, clippedRange.startOffset);

      const start = prefixRange.toString().length;
      const end = start + text.length;
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
      if (startedInReader) {
        handleSelection(true);
      }
    }

    function handlePointerCancel() {
      pointerDown = false;
      pointerStartedInReader = false;
    }

    function handleSelectionChange() {
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
  }, [onSelect, poem]);

  return (
    <div className="min-w-0">
      <Card
        ref={readerRef}
        className="min-h-155 gap-0 overflow-hidden border-border/60 bg-card py-0 shadow-sm"
      >
        <article className="mx-auto w-full max-w-xl px-7 py-12 sm:px-12 sm:py-14">
          <header className="mb-9 text-center">
            {/* 词牌、寓声、词题与作者各自来自独立字段，不拼成一条标题。 */}
            <div className="flex flex-wrap items-baseline justify-center gap-x-3 gap-y-1">
              <h1 className="font-serif text-4xl font-medium tracking-widest">
                {work.cipai ?? "词牌未核实"}
              </h1>
              {work.yusheng_title && (
                <span className="font-serif text-4xl font-normal tracking-normal text-muted-foreground">
                  {work.yusheng_title}
                </span>
              )}
            </div>
            {work.title && (
              <p className="mt-3 whitespace-pre-line font-serif text-lg leading-8 text-foreground/85">
                {work.title}
              </p>
            )}
            <p className="mt-3 text-sm text-muted-foreground">
              {work.author ?? "作者未核实"}
            </p>
            {work.review_status !== "reviewed" && (
              <p className="mt-2 text-xs text-muted-foreground/75">
                正文待校勘
              </p>
            )}
          </header>

          {work.prefaces.map((preface, index) => (
            <p key={index} className="mb-8 whitespace-pre-line font-serif text-sm leading-8 text-muted-foreground">
              {preface}
            </p>
          ))}

          <p
            ref={poemRef}
            className="cursor-text select-text whitespace-pre-line font-serif text-lg leading-[3] tracking-wide text-foreground/90 selection:bg-violet-200 selection:text-violet-950 dark:selection:bg-violet-400/40 dark:selection:text-white sm:text-xl"
          >
            {poem}
          </p>
        </article>
      </Card>

      <p className="mt-3 text-center text-xs text-muted-foreground">
        划选诗句，即可引用提问
      </p>
    </div>
  );
}
