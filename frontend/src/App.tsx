import { useState } from "react";
import { BookOpenText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";

import { poem } from "@/data/sample-poem";

import type { SelectedText } from "@/components/poem-reader";
import type { ChatMessage } from "@/components/chat-panel";
import type { PoemAnalysis } from "@/components/analysis-panel";

type ActiveView = "chat" | "analysis";

function App() {
  // 阅读选区与聊天
  const [selected, setSelected] = useState<SelectedText | null>(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // 右侧当前显示的视图
  const [activeView, setActiveView] = useState<ActiveView>("chat");

  // 整首赏析
  const [analysis, setAnalysis] = useState<PoemAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  function handleSend() {
    if (!question.trim()) return;

    setMessages((previous) => [
      ...previous,
      {
        question: question.trim(),
        quote: selected?.text ?? null,
      },
    ]);

    setQuestion("");
    setSelected(null);
  }

  async function handleAnalyze() {
    setActiveView("analysis");
    setAnalyzing(true);
    setAnalysisError("");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ poem }),
      });

      if (!response.ok) {
        const error = await response.json();

        throw new Error(
          typeof error.detail === "string"
            ? error.detail
            : `请求失败：HTTP ${response.status}`,
        );
      }

      const result: PoemAnalysis = await response.json();
      setAnalysis(result);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "赏析请求失败");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* 顶部导航 */}
      <header className="border-b border-border/50 bg-background/70 backdrop-blur-xl">
        <div className="mx-auto flex min-h-20 max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4 md:px-8">
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center rounded-2xl bg-foreground text-background shadow-lg shadow-black/10">
              <BookOpenText className="size-6" />
            </div>

            <div>
              <div className="text-xl font-semibold tracking-tight">
                Poeticus
              </div>

              <div className="text-xs tracking-wide text-muted-foreground">
                LITERATURE READING STUDIO
              </div>
            </div>
          </div>

          <ThemeSwitcher />
        </div>
      </header>

      {/* 页面主体 */}
      <main className="mx-auto w-full max-w-7xl px-5 pb-10 pt-10 md:px-8">
        <div className="mb-8">
          <div className="mb-3 text-xs font-medium uppercase tracking-widest text-violet-600 dark:text-violet-300">
            Your reading space
          </div>

          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            让阅读成为一场对话
          </h1>

          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            阅读、思考、提问，在诗歌中发现更多可能。
          </p>

          <Button className="mt-5" onClick={handleAnalyze} disabled={analyzing}>
            {analyzing ? "正在赏析……" : "整首赏析"}
          </Button>
        </div>

        {/* 左侧阅读器 + 右侧双视图 */}
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <PoemReader onSelect={setSelected} />

          <div className="min-w-0">
            {/* 右侧视图切换 */}
            <div
              className="mb-3 flex items-center gap-2"
              role="group"
              aria-label="右侧视图"
            >
              <Button
                type="button"
                variant={activeView === "chat" ? "default" : "ghost"}
                size="sm"
                aria-pressed={activeView === "chat"}
                onClick={() => setActiveView("chat")}
              >
                对话
              </Button>

              <Button
                type="button"
                variant={activeView === "analysis" ? "default" : "ghost"}
                size="sm"
                aria-pressed={activeView === "analysis"}
                onClick={() => setActiveView("analysis")}
              >
                赏析
              </Button>
            </div>

            {activeView === "chat" ? (
              <ChatPanel
                selected={selected}
                question={question}
                messages={messages}
                onQuestionChange={setQuestion}
                onClearQuote={() => setSelected(null)}
                onSend={handleSend}
              />
            ) : (
              <AnalysisPanel
                analysis={analysis}
                analyzing={analyzing}
                error={analysisError}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
