import { Button } from "@/components/ui/button";

export type ActiveView = "chat" | "analysis";

type ViewToolbarProps = {
  activeView: ActiveView;
  onViewChange: (view: ActiveView) => void;
  onAnalyze: () => void;
  analyzing: boolean;
  switching: boolean;
};

export function ViewToolbar({
  activeView,
  onViewChange,
  onAnalyze,
  analyzing,
  switching,
}: ViewToolbarProps) {
  return (
    <div
      className="mb-3 flex shrink-0 items-center gap-2"
      role="group"
      aria-label="右侧视图"
    >
      <Button
        type="button"
        variant={activeView === "chat" ? "default" : "ghost"}
        size="sm"
        aria-pressed={activeView === "chat"}
        onClick={() => onViewChange("chat")}
      >
        对话
      </Button>
      <Button
        type="button"
        variant={activeView === "analysis" ? "default" : "ghost"}
        size="sm"
        aria-pressed={activeView === "analysis"}
        onClick={() => onViewChange("analysis")}
      >
        赏析
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="ml-auto"
        onClick={onAnalyze}
        disabled={analyzing || switching}
      >
        {analyzing ? "正在生成……" : "生成整首赏析"}
      </Button>
    </div>
  );
}
