import type { CSSProperties, ElementType } from "react";

import "./analysis-animations.css";

type AnalysisTextEntranceProps<T extends ElementType> = {
  as: T;
  text: string;
  animate: boolean;
  className?: string;
};

export function AnalysisTextEntrance<T extends ElementType>({
  as,
  text,
  animate,
  className,
}: AnalysisTextEntranceProps<T>) {
  const Component = as;

  if (!animate) {
    return <Component className={className}>{text}</Component>;
  }

  return (
    <Component className={className} aria-label={text}>
      {Array.from(text).map((character, index) => (
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
      ))}
    </Component>
  );
}
