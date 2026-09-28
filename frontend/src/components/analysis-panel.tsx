import { BookOpenText, LoaderCircle, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";

export type PoemAnalysis = {
  translation: string;
  glosses: {
    term: string;
    explanation: string;
  }[];
  commentary: string;
};

type AnalysisPanelProps = {
  analysis: PoemAnalysis | null;
  analyzing: boolean;
  error: string;
};

export function AnalysisPanel({
  analysis,
  analyzing,
  error,
}: AnalysisPanelProps) {
  return (
    <Card className="flex h-165 min-h-0 flex-col gap-0 overflow-hidden border-border/60 bg-card/90 py-0 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/20">
      {/* 顶部标题 */}
      <header className="flex shrink-0 items-center gap-3 border-b border-border/60 px-5 py-5">
        <div className="flex size-10 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-600 dark:text-violet-300">
          <BookOpenText className="size-5" />
        </div>

        <div>
          <h2 className="text-sm font-semibold">整首赏析</h2>
          <p className="text-xs text-muted-foreground">
            译文、词语注释与文学赏析
          </p>
        </div>
      </header>

      {/* 赏析内容 */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-7">
        {analyzing ? (
          <div
            role="status"
            className="flex h-full flex-col items-center justify-center gap-4 text-center"
          >
            <LoaderCircle className="size-8 animate-spin text-violet-500" />

            <div>
              <p className="font-medium">正在阅读这首诗……</p>
              <p className="mt-2 text-sm text-muted-foreground">
                AI 正在生成译文、注释和文学赏析
              </p>
            </div>
          </div>
        ) : error ? (
          <div role="alert" className="rounded-xl bg-destructive/10 p-4">
            <h3 className="font-medium text-destructive">赏析失败</h3>
            <p className="mt-2 text-sm leading-7 text-destructive">{error}</p>
          </div>
        ) : analysis ? (
          <div className="space-y-10">
            {/* 现代汉语译文 */}
            <section>
              <div className="mb-4 flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-violet-500" />
                <h3 className="text-base font-semibold">现代汉语译文</h3>
              </div>

              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.translation}
              </p>
            </section>

            <div className="border-t border-border/60" />

            {/* 词语注释 */}
            <section>
              <div className="mb-5 flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-violet-500" />
                <h3 className="text-base font-semibold">词语注释</h3>
              </div>

              {analysis.glosses.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  本次赏析没有需要单独解释的词语。
                </p>
              ) : (
                <div className="space-y-4">
                  {analysis.glosses.map((gloss, index) => (
                    <div
                      key={index}
                      className="border-b border-border/50 pb-4 last:border-0 last:pb-0"
                    >
                      <h4 className="mb-1 font-serif text-sm font-semibold">
                        {gloss.term}
                      </h4>

                      <p className="text-sm leading-7 text-muted-foreground">
                        {gloss.explanation}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <div className="border-t border-border/60" />

            {/* 文学赏析 */}
            <section>
              <div className="mb-4 flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-violet-500" />
                <h3 className="text-base font-semibold">文学赏析</h3>
              </div>

              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.commentary}
              </p>
            </section>
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex size-14 items-center justify-center rounded-3xl bg-violet-500/10">
              <Sparkles className="size-7 text-violet-500" />
            </div>

            <div className="max-w-xs space-y-2">
              <h3 className="font-medium">尚未生成赏析</h3>

              <p className="text-sm leading-7 text-muted-foreground">
                点击页面上方的「整首赏析」，
                即可生成这首诗的译文、注释和文学赏析。
              </p>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
