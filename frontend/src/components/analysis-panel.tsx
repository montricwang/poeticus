import { LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
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
  onAnalyze: () => void;
  switching: boolean;
  fillAvailableHeight?: boolean;
  className?: string;
};

export function AnalysisPanel({
  analysis,
  analyzing,
  error,
  limitNotice,
  onAnalyze,
  switching,
  fillAvailableHeight = false,
  className,
}: AnalysisPanelProps) {
  return (
    <section
      aria-label="整首赏析"
      className={cn(
        "flex min-h-0 min-w-0 flex-col bg-transparent",
        fillAvailableHeight
          ? "flex-1"
          : "max-h-[min(42rem,calc(100dvh-10rem))]",
        className,
      )}
    >
      <div
        className={cn(
          "min-h-0",
          fillAvailableHeight
            ? "flex-1 overflow-y-auto py-4 pr-2"
            : "overflow-y-auto py-4 pr-2",
        )}
      >
        {analyzing ? (
          <div
            role="status"
            className="flex min-h-72 flex-col items-center justify-center gap-4 text-center"
          >
            <LoaderCircle className="size-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              正在生成译文、注释和文学赏析……
            </p>
          </div>
        ) : error ? (
          <div
            role={limitNotice ? "status" : "alert"}
            className={cn(
              "mx-auto max-w-md rounded-xl p-4",
              limitNotice
                ? "bg-muted/30 text-foreground"
                : "bg-destructive/10 text-destructive",
            )}
          >
            <h3 className="font-medium">
              {limitNotice ? "稍等一会儿" : "赏析失败"}
            </h3>
            <p className="mt-2 text-sm leading-7">{error}</p>
            {!limitNotice && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={onAnalyze}
                disabled={switching}
              >
                重新生成
              </Button>
            )}
          </div>
        ) : analysis ? (
          <div className="space-y-10">
            <section>
              <h3 className="mb-4 text-base font-semibold">现代汉语译文</h3>
              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.translation}
              </p>
            </section>

            <div className="h-px w-12 bg-border/80" aria-hidden="true" />

            <section>
              <h3 className="mb-5 text-base font-semibold">词语注释</h3>
              {analysis.glosses.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  本次赏析没有需要单独解释的词语。
                </p>
              ) : (
                <div className="space-y-4">
                  {analysis.glosses.map((gloss, index) => (
                    <div key={index}>
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

            <div className="h-px w-12 bg-border/80" aria-hidden="true" />

            <section>
              <h3 className="mb-4 text-base font-semibold">文学赏析</h3>
              <p className="whitespace-pre-wrap text-sm leading-8 text-foreground/85">
                {analysis.commentary}
              </p>
            </section>
          </div>
        ) : (
          <div className="flex min-h-72 items-center justify-center text-center">
            <div className="space-y-4">
              <p className="text-sm leading-7 text-muted-foreground">
                生成译文、词语注释与文学赏析。
              </p>
              <Button
                type="button"
                onClick={onAnalyze}
                disabled={switching}
              >
                生成整首赏析
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
