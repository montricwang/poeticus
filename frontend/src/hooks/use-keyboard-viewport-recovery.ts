import { useCallback, useEffect, useRef } from "react";

const KEYBOARD_HEIGHT_DELTA = 120;

function isAppleTouchDevice() {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function useKeyboardViewportRecovery() {
  const baselineHeightRef = useRef<number | null>(null);
  const keyboardSeenRef = useRef(false);
  const pendingRestoreRef = useRef(false);
  const timerIdsRef = useRef<number[]>([]);

  const nudgeRootScroll = useCallback(() => {
    const scrollingElement = document.scrollingElement;
    if (!(scrollingElement instanceof HTMLElement)) return;

    const top = scrollingElement.scrollTop;
    const maxTop = Math.max(
      0,
      scrollingElement.scrollHeight - scrollingElement.clientHeight,
    );
    if (maxTop <= 0) return;

    const nudgedTop = top > 0 ? top - 1 : Math.min(1, maxTop);
    scrollingElement.scrollTop = nudgedTop;

    window.requestAnimationFrame(() => {
      scrollingElement.scrollTop = top;
    });
  }, []);

  const tryRestoreViewport = useCallback(() => {
    if (!isAppleTouchDevice()) return;

    const viewport = window.visualViewport;
    const baselineHeight = baselineHeightRef.current;
    if (
      !viewport ||
      baselineHeight === null ||
      !keyboardSeenRef.current ||
      !pendingRestoreRef.current
    ) {
      return;
    }

    // WebKit 可能先触发 resize，再更新 visualViewport.height；
    // 放到 rAF 中检查，等键盘关闭后的完整视口真正恢复。
    window.requestAnimationFrame(() => {
      if (viewport.height < baselineHeight - 2) return;

      pendingRestoreRef.current = false;
      keyboardSeenRef.current = false;
      baselineHeightRef.current = null;

      // iOS / iPadOS 某些 WebKit 版本在键盘关闭后会留下旧的
      // visual viewport 命中坐标。一次不可见的 1px 根滚动可以迫使
      // compositor / hit-testing 与当前视口重新同步。
      window.requestAnimationFrame(nudgeRootScroll);
    });
  }, [nudgeRootScroll]);

  useEffect(() => {
    if (!isAppleTouchDevice()) return;

    const viewport = window.visualViewport;
    if (!viewport) return;
    const visualViewport = viewport;

    function handleResize() {
      const baselineHeight = baselineHeightRef.current;
      if (
        baselineHeight !== null &&
        visualViewport.height < baselineHeight - KEYBOARD_HEIGHT_DELTA
      ) {
        keyboardSeenRef.current = true;
        pendingRestoreRef.current = true;
      }

      tryRestoreViewport();
    }

    visualViewport.addEventListener("resize", handleResize);

    return () => {
      visualViewport.removeEventListener("resize", handleResize);
      for (const timerId of timerIdsRef.current) {
        window.clearTimeout(timerId);
      }
      timerIdsRef.current = [];
    };
  }, [tryRestoreViewport]);

  const handleFocus = useCallback(() => {
    if (!isAppleTouchDevice()) return;

    const viewport = window.visualViewport;
    baselineHeightRef.current = viewport?.height ?? window.innerHeight;
    keyboardSeenRef.current = false;
    pendingRestoreRef.current = false;
  }, []);

  const handleBlur = useCallback(() => {
    if (!isAppleTouchDevice() || !keyboardSeenRef.current) return;

    pendingRestoreRef.current = true;

    // Safari 的 viewport resize 有时会晚于 blur/键盘动画结束；
    // 补两次延迟检查，仍只在高度已经恢复时执行修复。
    timerIdsRef.current.push(
      window.setTimeout(tryRestoreViewport, 80),
      window.setTimeout(tryRestoreViewport, 240),
    );
  }, [tryRestoreViewport]);

  return { handleFocus, handleBlur };
}
