import type { ReactNode } from "react";
import { MessageCircle, X } from "lucide-react";
import { Dialog } from "radix-ui";

import { Button } from "@/components/ui/button";

type MobileDiscussionSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasUnreadReply: boolean;
  hasSelection: boolean;
  children: ReactNode;
};

export function MobileDiscussionSheet({
  open,
  onOpenChange,
  hasUnreadReply,
  hasSelection,
  children,
}: MobileDiscussionSheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <Button
          type="button"
          size="lg"
          className="fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 rounded-full px-4 shadow-lg"
          aria-label={hasSelection ? "打开对话并使用已选诗句提问" : "打开阅读对话"}
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
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[1px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0" />

        <Dialog.Content className="fixed inset-x-0 bottom-0 z-[60] flex h-[92dvh] max-h-[92dvh] min-h-0 flex-col rounded-t-2xl border border-b-0 border-border/70 bg-background shadow-2xl outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom sm:left-1/2 sm:max-w-2xl sm:-translate-x-1/2">
          <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-4 py-3">
            <div>
              <Dialog.Title className="text-sm font-medium">阅读讨论</Dialog.Title>
              <Dialog.Description className="sr-only">
                与当前作品对话，或查看整首赏析。
              </Dialog.Description>
            </div>

            <Dialog.Close asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="rounded-full"
                aria-label="关闭阅读讨论"
              >
                <X className="size-4" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="flex min-h-0 flex-1 flex-col px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
