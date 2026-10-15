import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { poemText } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'
import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'

type DailyRecommendationProps = {
  poem: Poem | null
  loading: boolean
  error: string
  disabled: boolean
  onRead: (id: string) => void
}

/**
 * 两种排版仅影响首页预览，不改变作品原文与阅读室。
 * 样式一沿用句读分行，样式二为连续换列；手机的样式二只展示正文节选。
 */
export function DailyRecommendation({
  poem,
  loading,
  error,
  disabled,
  onRead,
}: DailyRecommendationProps) {
  const [layout, setLayout] = useState<'phrases' | 'continuous'>('continuous')
  const continuous = layout === 'continuous'

  return (
    <section aria-label="推荐作品" className="relative py-16 sm:py-24 lg:py-0">
      <div
        role="group"
        aria-label="推荐作品排版方式"
        className="absolute right-0 top-2 z-10 flex items-center gap-1 rounded-md border border-border/70 bg-background/95 p-1 text-xs text-muted-foreground"
      >
        <button
          type="button"
          aria-pressed={!continuous}
          onClick={() => setLayout('phrases')}
          className={`rounded px-2 py-1 transition-colors ${!continuous ? 'bg-accent text-foreground' : 'hover:text-foreground'}`}
        >
          样式一
        </button>
        <button
          type="button"
          aria-pressed={continuous}
          onClick={() => setLayout('continuous')}
          className={`rounded px-2 py-1 transition-colors ${continuous ? 'bg-accent text-foreground' : 'hover:text-foreground'}`}
        >
          样式二
        </button>
      </div>
      {poem ? (
        // 样式一保留可滚动全文；样式二在手机截取短文，并禁止内部横向滚动。
        <div className="mx-auto flex w-max max-w-full items-end gap-4 sm:gap-8">
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => onRead(poem.id)}
            className="h-auto shrink-0 self-end px-3 py-4 text-xs [writing-mode:vertical-rl]"
          >
            读这首词
          </Button>
          <div
            dir="rtl"
            className={`poeticus-scrollport min-w-0 ${continuous ? 'overflow-x-hidden sm:overflow-x-auto' : 'overflow-x-auto'}`}
          >
            <article
              dir="ltr"
              lang="zh-CN"
              className={`poem-reader home-featured-poem w-max font-serif lg:[--reader-poem-line-height:1.4] lg:[--reader-poem-letter-spacing:0.12em] lg:[--reader-preface-size:0.875rem] lg:[--reader-preface-line-height:1.6] lg:[--reader-author-size:1.125rem] lg:[--reader-title-size:1.25rem] ${continuous ? '[--reader-poem-line-height:1.4] [--reader-poem-letter-spacing:0.12em]' : ''}`}
              style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
            >
              <header className={`ml-7 lg:ml-2.5 ${continuous ? 'hidden sm:block' : ''}`}>
                {/* 与横排阅读器一致：寓声为主标题，词牌另作辅助标题。 */}
                <h2 className="poem-reader-heading font-serif lg:ml-2.5">
                  {poem.yusheng_title ?? poem.cipai ?? '词牌未核实'}
                </h2>
                {poem.yusheng_title && poem.cipai && (
                  <p className="poem-reader-secondary-heading ml-3 text-muted-foreground lg:ml-2.5">
                    {poem.cipai}
                  </p>
                )}
                {poem.title && (
                  <p className="poem-reader-title ml-3 whitespace-pre-line font-serif text-foreground/85 lg:ml-2.5 lg:mt-[var(--reader-poem-size)]">
                    {poem.title}
                  </p>
                )}
                <p className="poem-reader-author ml-3 font-sans text-muted-foreground lg:ml-0 lg:mt-[var(--reader-poem-size)]">
                  {poem.author ?? '作者未核实'}
                </p>
              </header>
              {/* 小序最多占约 11 个正文字高；1.12 对应正文 0.12em 的字距。 */}
              {poem.prefaces.map((preface, index) => (
                <p
                  key={index}
                  className={`ml-7 lg:ml-9 lg:mt-[var(--reader-poem-size)] max-h-[min(26rem,65dvh)] lg:max-h-[calc(11*var(--reader-poem-size)*1.12)] whitespace-pre-line font-serif text-[length:var(--reader-preface-size)] font-normal leading-[var(--reader-preface-line-height)] text-muted-foreground lg:[letter-spacing:0.08em] ${continuous ? 'hidden sm:block' : ''}`}
                >
                  {preface}
                </p>
              ))}
              {continuous ? (
                <ContinuousPoemBody poem={poem} />
              ) : (
                <div className="poem-reader-body !mx-0 !w-max max-w-none text-foreground/90 lg:pt-[var(--reader-poem-size)]">
                  {buildPoemLines(poemText(poem)).map((line) => (
                    <span
                      key={line.start}
                      className={
                        'poem-reader-line' + (line.sourceGapBefore ? ' poem-reader-source-gap' : '')
                      }
                    >
                      {buildPoemTextRuns(line.text).map((run, index) =>
                        run.punctuation ? (
                          <span key={index} className="poem-reader-punctuation">
                            {run.text}
                          </span>
                        ) : (
                          <span key={index}>{run.text}</span>
                        ),
                      )}
                    </span>
                  ))}
                </div>
              )}
            </article>
          </div>
        </div>
      ) : (
        <p role="status" className="py-20 text-center text-sm text-muted-foreground">
          {loading ? '正在寻一首词……' : error || '暂时没有推荐作品'}
        </p>
      )}
    </section>
  )
}

/** 一句里的现代标点缩为附在前一个字旁的圈点，不另占竖排字格。 */
type ClassicGlyph = { char: string; mark: string }

function classicGlyphs(text: string): ClassicGlyph[] {
  const glyphs: ClassicGlyph[] = []
  for (const char of text) {
    if (
      /^[，、。？！；：]$/u.test(char) &&
      glyphs.length &&
      glyphs[glyphs.length - 1].char !== '　'
    ) {
      glyphs[glyphs.length - 1].mark += char
    } else {
      glyphs.push({ char, mark: '' })
    }
  }
  return glyphs
}

/** 手机不横向浏览：在接近上限的句末结束，末尾省略号只属于预览。 */
function mobilePreview(segments: string[], maxCharacters = 44): string {
  const text = segments.join('　　')
  const characters = Array.from(text)
  if (characters.length <= maxCharacters) return text
  let end = maxCharacters
  for (let index = maxCharacters; index >= Math.floor(maxCharacters * 0.7); index--) {
    if (/[，。？！；]/u.test(characters[index - 1])) {
      end = index
      break
    }
  }
  return characters.slice(0, end).join('').trimEnd() + '…'
}

function ClassicText({ text }: { text: string }) {
  return (
    <>
      {classicGlyphs(text).map(({ char, mark }, index) => (
        <span key={index} className="home-classic-glyph">
          {char}
          {mark && (
            <span className="home-classic-mark" aria-label={mark}>
              {mark}
            </span>
          )}
        </span>
      ))}
    </>
  )
}

function ContinuousPoemBody({ poem }: { poem: Poem }) {
  const text = poem.body_segments.join('　　')
  return (
    <>
      <div className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 sm:hidden">
        <ClassicText text={mobilePreview(poem.body_segments)} />
      </div>
      <div className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 max-sm:hidden sm:pt-[var(--reader-poem-size)]">
        <ClassicText text={text} />
      </div>
    </>
  )
}
