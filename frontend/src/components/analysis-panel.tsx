import { LoaderCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

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
  limitNotice: boolean;
  fillAvailableHeight?: boolean;
  className?: string;
};

export function AnalysisPanel({
  analysis,
  analyzing,
  error,
  limitNotice,
  fillAvailableHeight = false,
  className,
}: AnalysisPanelProps) {
  return (
    <Card
      className={cn(
        "flex min-h-0 flex-col gap-0 overflow-hidden border-border/60 bg-card py-0 shadow-sm",
        fillAvailableHeight ? "h-full flex-1" : "h-165",
        className,
      )}
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-7">
        {analyzing ? (
          <div
            role="status"
            className="flex h-full flex-col items-center justify-center gap-4 text-center"
          >
            <LoaderCircle className="size-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">正在生成译文、注释和文学赏析……</p>
          </div>
        ) : error ? (
          <div
            role={limitNotice ? "status" : "alert"}
            className={`rounded-xl p-4 ${limitNotice ? "border border-border/60 bg-muted/30" : "bg-destructive/10"}`}
          >
            <h3 className={`font-medium ${limitNotice ? "text-foreground" : "text-destructive"}`}>
              {limitNotice ? "稍等一会儿" : "赏析失败"}
            </h3>
            <p className={`mt-2 text-sm leading-7 ${limitNotice ? "text-muted-foreground" : "text-destructive"}`}>
              {error}
            </p>
          </div>
        ) : analysis ? (
          <div className="space-y-10">
            <section>
              <h3 className="mb-4 text-base font-semibold">现代汉语译文</h3>
              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.translation}
              </p>
            </section>

            <div className="border-t border-border/60" />

            <section>
              <h3 className="mb-5 text-base font-semibold">词语注释</h3>
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

            <section>
              <h3 className="mb-4 text-base font-semibold">文学赏析</h3>
              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.commentary}
              </p>
            </section>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-center">
            <p className="max-w-xs text-sm leading-7 text-muted-foreground">
              点击右上方「生成整首赏析」，查看译文、词语注释与文学赏析。
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}
