import type { ReactNode } from "react";
import { MessageCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";

type MobileDiscussionDockProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasUnreadReply: boolean;
  hasSelection: boolean;
  hasConversation: boolean;
  children: ReactNode;
};

export function MobileDiscussionDock({
  open,
  onOpenChange,
  hasUnreadReply,
  hasSelection,
  hasConversation,
  children,
}: MobileDiscussionDockProps) {
  return (
    <>
      <Button
        type="button"
        size="lg"
        variant="outline"
        className={
          "fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-[60] rounded-md bg-background/95 px-4 shadow-sm backdrop-blur-sm " +
          "transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none " +
          (open ? "pointer-events-none scale-100 opacity-0" : "scale-100 opacity-100")
        }
        aria-controls="mobile-discussion-dock"
        aria-expanded={open}
        aria-hidden={open}
        tabIndex={open ? -1 : undefined}
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

      <section
        id="mobile-discussion-dock"
        aria-label="阅读讨论"
        aria-hidden={!open}
        inert={!open}
        className={
          "fixed inset-x-0 bottom-0 z-40 flex min-h-0 flex-col bg-background " +
          "will-change-transform transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
          (hasConversation
            ? "h-[clamp(18rem,44dvh,30rem)] "
            : hasSelection
              ? "h-[clamp(16rem,36dvh,22rem)] "
              : "h-[clamp(12rem,26dvh,15rem)] ") +
          (open
            ? "translate-y-0"
            : "pointer-events-none translate-y-full")
        }
      >
        <div className="mx-4 h-px shrink-0 bg-border/70" aria-hidden="true" />

        <div className="flex shrink-0 items-center justify-between px-4 py-2.5">
          <h2 className="text-sm font-medium">阅读讨论</h2>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-md"
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
