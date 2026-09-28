import { useRef } from "react";
import { BookOpen } from "lucide-react";
import { Card } from "@/components/ui/card";

const poem = `风卷珠帘自上钩，萧萧乱叶报新秋。
独携纤手上高楼。

缺月向人舒窈窕，三星当户照绸缪。
香生雾縠见纤柔。`;

export type SelectedText = {
  text: string;
  start: number;
  end: number;
};

type PoemReaderProps = {
  onSelect: (selection: SelectedText) => void;
};

export function PoemReader({ onSelect }: PoemReaderProps) {
  const poemRef = useRef<HTMLParagraphElement>(null);

  function handleSelection() {
    const selection = window.getSelection();

    if (!selection || selection.isCollapsed) return;

    const range = selection.getRangeAt(0);
    const textNode = poemRef.current?.firstChild;

    if (range.startContainer !== textNode || range.endContainer !== textNode) {
      return;
    }

    const start = range.startOffset;
    const end = range.endOffset;
    const text = poem.slice(start, end);

    if (!text.trim()) return;

    onSelect({ text, start, end });
  }

  return (
    <Card className="min-h-[620px] gap-0 overflow-hidden border-border/60 bg-card/90 py-0 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/20">
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
          onMouseUp={handleSelection}
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
