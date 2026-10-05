import { useCallback, useEffect, useRef } from "react";

const KEYBOARD_SHRINK_DELTA = 120;
const KEYBOARD_REOPEN_DELTA = 80;
const RECOVERY_DELAYS = [0, 120, 320, 650] as const;

function isAppleTouchDevice() {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function useKeyboardViewportRecovery() {
  const baselineHeightRef = useRef<number | null>(null);
  const minimumHeightRef = useRef<number | null>(null);
  const keyboardSeenRef = useRef(false);
  const recoveryScheduledRef = useRef(false);
  const timerIdsRef = useRef<number[]>([]);

  const forceViewportSync = useCallback(() => {
    const scrollingElement = document.scrollingElement;
    if (!scrollingElement) return;

    const top = window.scrollY;
    const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
    const maxTop = Math.max(0, scrollingElement.scrollHeight - viewportHeight);
    if (maxTop <= 0) return;

    // WebKit 的 keyboard-dismiss hit-testing bug 需要一次真正的 window
    // scroll 才会让 visual viewport、compositor 与触摸命中重新对齐。
    // 根据当前位置选择仍在合法范围内的 1px 方向，再立即还原。
    const delta = top < maxTop ? 1 : top > 0 ? -1 : 0;
    if (delta === 0) return;

    window.scrollBy(0, delta);
    window.requestAnimationFrame(() => {
      window.scrollBy(0, -delta);
    });
  }, []);

  const scheduleRecovery = useCallback(() => {
    if (!isAppleTouchDevice() || recoveryScheduledRef.current) return;

    recoveryScheduledRef.current = true;

    for (const delay of RECOVERY_DELAYS) {
      const timerId = window.setTimeout(() => {
        // 强制读取一次布局，避免连续 scroll 被 WebKit 当作无效写入合并掉。
        void document.documentElement.getBoundingClientRect().height;
        forceViewportSync();

        if (delay === RECOVERY_DELAYS[RECOVERY_DELAYS.length - 1]) {
          recoveryScheduledRef.current = false;
          keyboardSeenRef.current = false;
          minimumHeightRef.current = null;
          baselineHeightRef.current =
            window.visualViewport?.height ?? window.innerHeight;
        }
      }, delay);

      timerIdsRef.current.push(timerId);
    }
  }, [forceViewportSync]);

  useEffect(() => {
    if (!isAppleTouchDevice()) return;

    const viewport = window.visualViewport;
    if (!viewport) return;
    const visualViewport = viewport;

    function handleViewportChange() {
      const currentHeight = visualViewport.height;
      const baselineHeight = baselineHeightRef.current;

      if (baselineHeight === null) {
        baselineHeightRef.current = currentHeight;
        minimumHeightRef.current = currentHeight;
        return;
      }

      if (currentHeight < baselineHeight - KEYBOARD_SHRINK_DELTA) {
        keyboardSeenRef.current = true;
        minimumHeightRef.current = Math.min(
          minimumHeightRef.current ?? currentHeight,
          currentHeight,
        );
        return;
      }

      const minimumHeight = minimumHeightRef.current;
      if (
        keyboardSeenRef.current &&
        minimumHeight !== null &&
        currentHeight > minimumHeight + KEYBOARD_REOPEN_DELTA
      ) {
        // 不要求恢复到原 baseline：WebKit 自己的 bug 就可能让 viewport
        // 在键盘关闭后停在错误高度。只要确认正在从键盘态恢复就开始修复。
        scheduleRecovery();
      }
    }

    visualViewport.addEventListener("resize", handleViewportChange);
    visualViewport.addEventListener("scroll", handleViewportChange);

    return () => {
      visualViewport.removeEventListener("resize", handleViewportChange);
      visualViewport.removeEventListener("scroll", handleViewportChange);
      for (const timerId of timerIdsRef.current) {
        window.clearTimeout(timerId);
      }
      timerIdsRef.current = [];
    };
  }, [scheduleRecovery]);

  const handleFocus = useCallback(() => {
    if (!isAppleTouchDevice()) return;

    const currentHeight =
      window.visualViewport?.height ?? window.innerHeight;

    baselineHeightRef.current = currentHeight;
    minimumHeightRef.current = currentHeight;
    keyboardSeenRef.current = false;
    recoveryScheduledRef.current = false;
  }, []);

  const handleBlur = useCallback(() => {
    // 收起键盘并不保证 textarea 失焦；blur 这里只作为额外保险。
    if (keyboardSeenRef.current) {
      scheduleRecovery();
    }
  }, [scheduleRecovery]);

  return { handleFocus, handleBlur };
}
