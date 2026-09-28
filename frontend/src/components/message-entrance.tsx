import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import "./chat-animations.css";

type MessageEntranceProps = {
  animationId: string;
  seenAnimationsRef: RefObject<Set<string>>;
  enabled?: boolean;
  children: ReactNode;
};

export function MessageEntrance({
  animationId,
  seenAnimationsRef,
  enabled = true,
  children,
}: MessageEntranceProps) {
  const elementRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!enabled || seenAnimationsRef.current.has(animationId)) return;

    // 登记后再播放，切换到赏析再返回时不会重播旧动画。
    seenAnimationsRef.current.add(animationId);
    elementRef.current?.classList.add("poeticus-message-enter");
  }, [animationId, enabled, seenAnimationsRef]);

  return <div ref={elementRef}>{children}</div>;
}
