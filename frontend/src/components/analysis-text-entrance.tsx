import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import "./analysis-animations.css";

type AnalysisRevealProps = {
  animate: boolean;
  children: (revealed: boolean) => ReactNode;
};

export function AnalysisReveal({
  animate,
  children,
}: AnalysisRevealProps) {
  const elementRef = useRef<HTMLDivElement>(null);
  const [revealed, setRevealed] = useState(!animate);

  useEffect(() => {
    if (!animate) {
      setRevealed(true);
      return;
    }

    const element = elementRef.current;
    if (!element) return;

    if (!("IntersectionObserver" in window)) {
      setRevealed(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setRevealed(true);
        observer.disconnect();
      },
      {
        threshold: 0.08,
        rootMargin: "0px 0px -6% 0px",
      },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [animate]);

  return (
    <div
      ref={elementRef}
      className={
        animate
          ? revealed
            ? "poeticus-analysis-block-enter"
            : "poeticus-analysis-block-pending"
          : undefined
      }
    >
      {children(revealed)}
    </div>
  );
}

type AnalysisTextEntranceProps = {
  as: "p" | "h3" | "h4";
  text: string;
  animate: boolean;
  className?: string;
};

export function AnalysisTextEntrance({
  as,
  text,
  animate,
  className,
}: AnalysisTextEntranceProps) {
  const content = animate
    ? Array.from(text).map((character, index) => (
        <span
          key={index}
          aria-hidden="true"
          className="poeticus-analysis-char-enter"
          style={
            {
              "--analysis-char-delay": `${index * 2}ms`,
            } as CSSProperties
          }
        >
          {character}
        </span>
      ))
    : text;

  if (as === "h3") {
    return (
      <h3 className={className} aria-label={animate ? text : undefined}>
        {content}
      </h3>
    );
  }

  if (as === "h4") {
    return (
      <h4 className={className} aria-label={animate ? text : undefined}>
        {content}
      </h4>
    );
  }

  return (
    <p className={className} aria-label={animate ? text : undefined}>
      {content}
    </p>
  );
}
