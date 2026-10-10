import { useRef } from 'react'
import { PoemBody } from '@/components/poem-body'

import { poemText } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'
import type { SelectedText } from '@/types/poem'

type PoemReaderProps = {
  work: Poem
  onSelect: (selection: SelectedText) => void
}

export function PoemReader({ work, onSelect }: PoemReaderProps) {
  const poem = poemText(work)
  const readerRef = useRef<HTMLDivElement>(null)
  return (
    <div className="poem-reader min-w-0 lg:flex lg:min-h-[var(--desktop-reading-stage-min-height)] lg:flex-1 lg:flex-col">
      <div
        ref={readerRef}
        className="bg-transparent lg:flex lg:flex-1 lg:flex-col lg:justify-center"
      >
        <article className="poem-reader-page mx-auto w-full min-w-0 px-4 sm:px-8">
          <header className="poem-reader-header text-center">
            {/* 有寓声时尊重来源题头次序：寓声为主，原词牌为辅。 */}
            <div className="poem-reader-heading-row flex flex-wrap items-baseline justify-center">
              <h1 className="poem-reader-heading font-serif">
                {work.yusheng_title ?? work.cipai ?? '词牌未核实'}
              </h1>
              {work.yusheng_title && work.cipai && (
                <span className="poem-reader-secondary-heading font-serif text-muted-foreground">
                  {work.cipai}
                </span>
              )}
            </div>
            {work.title && (
              <p className="poem-reader-title whitespace-pre-line font-serif text-foreground/85">
                {work.title}
              </p>
            )}
            <p className="poem-reader-author text-muted-foreground">
              {work.author ?? '作者未核实'}
            </p>
            {work.review_status !== 'reviewed' && (
              <p className="poem-reader-status text-muted-foreground/75">正文待校勘</p>
            )}
          </header>

          {work.prefaces.map((preface, index) => (
            <p
              key={index}
              className="poem-reader-preface whitespace-pre-line font-serif text-muted-foreground"
            >
              {preface}
            </p>
          ))}

          <PoemBody poem={poem} selectionScopeRef={readerRef} onSelect={onSelect} />
        </article>
      </div>


    </div>
  )
}
