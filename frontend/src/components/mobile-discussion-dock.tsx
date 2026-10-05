import type { ReactNode } from "react";
import { MessageCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";

type MobileDiscussionDockProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasUnreadReply: boolean;
  hasSelection: boolean;
  children: ReactNode;
};

export function MobileDiscussionDock({
  open,
  onOpenChange,
  hasUnreadReply,
  hasSelection,
  children,
}: MobileDiscussionDockProps) {
  return (
    <>
      {!open && (
        <Button
          type="button"
          size="lg"
          className="fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 rounded-full px-4 shadow-lg"
          aria-controls="mobile-discussion-dock"
          aria-expanded={false}
          aria-label={hasSelection ? "打开讨论并使用已选诗句提问" : "打开阅读讨论"}
          onClick={() => onOpenChange(true)}
        >
          <MessageCircle className="size-4" aria-hidden="true" />
          <span>{hasSelection ? "提问" : "对话"}</span>
          {hasUnreadReply && (
            <span
              className="size-2 rounded-full bg-violet-300"
              aria-label="有新回复"
            />
          )}
        </Button>
      )}

      <section
        id="mobile-discussion-dock"
        aria-label="阅读讨论"
        aria-hidden={!open}
        inert={!open}
        className={
          "fixed inset-x-0 bottom-0 z-40 flex h-[clamp(16rem,42dvh,28rem)] min-h-0 flex-col " +
          "border-t border-border/70 bg-background " +
          "transition-transform duration-300 ease-out motion-reduce:transition-none " +
          (open
            ? "translate-y-0"
            : "pointer-events-none translate-y-full")
        }
      >
        <div className="flex shrink-0 items-center justify-between px-4 py-2.5">
          <h2 className="text-sm font-medium">阅读讨论</h2>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-full"
            aria-label="收起阅读讨论"
            onClick={() => onOpenChange(false)}
          >
            <X className="size-4" />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </section>
    </>
  );
}
