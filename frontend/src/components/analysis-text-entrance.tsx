import type { CSSProperties } from "react";

import "./analysis-animations.css";

type AnalysisTextEntranceProps = {
  as: "p" | "h4";
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
