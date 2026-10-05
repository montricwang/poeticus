import type { ReactNode } from "react";

type MobileDiscussionScreenProps = {
  open: boolean;
  children: ReactNode;
};

export function MobileDiscussionScreen({
  open,
  children,
}: MobileDiscussionScreenProps) {
  return (
    <section
      id="mobile-discussion-screen"
      aria-label="阅读讨论"
      aria-hidden={!open}
      inert={!open}
      className={
        "absolute inset-0 z-20 flex min-h-0 flex-col bg-background " +
        "transition-opacity duration-[520ms] ease-[cubic-bezier(0.22,1,0.36,1)] " +
        "md:transition-transform md:duration-400 md:ease-[cubic-bezier(0.22,1,0.36,1)] " +
        "motion-reduce:transition-none " +
        (open
          ? "pointer-events-auto opacity-100 md:translate-x-0 md:opacity-100"
          : "pointer-events-none opacity-0 md:translate-x-full md:opacity-100")
      }
    >
      <div className="flex min-h-0 flex-1 flex-col px-4 pt-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {children}
      </div>
    </section>
  );
}
