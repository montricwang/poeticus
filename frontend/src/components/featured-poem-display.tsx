import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import type { Poem } from '@/data/poem-library'
import { buildHomeBookTitleRuns } from '@/lib/home-book-title'
import type { HomeBookTitleRun } from '@/lib/home-book-title'
import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { arrangeHomeColumns } from '@/lib/home-preview-columns'

const HOME_MAX_BODY_COLUMNS = 5

/** 作品文本只负责竖排与两种断列规则，不负责按钮和首页留白。 */
export function FeaturedPoemDisplay({ poem, continuous }: { poem: Poem; continuous: boolean }) {
  const poemScrollport = useRef<HTMLDivElement>(null)
  const [previewSegments, setPreviewSegments] = useState<string[] | null>(null)

  // 手机端沿用已封板的断列/节选规则，不参与桌面端的宽度计算。
  useLayoutEffect(() => {
    const scrollport = poemScrollport.current
    const article = scrollport?.querySelector('article')
    if (!scrollport || !article || !continuous) return

    const fits = (segments: string[]) => {
      const body = scrollport.querySelector<HTMLElement>('.home-classic-body')
      const budget = body && getHomeMobileColumnBudget(body, segments)
      if (!budget) return false
      const text = segments.join('\u3000')
      return !!(
        arrangeHomeColumns(text, budget.capacity, budget.maxColumns, {
          minInkLength: budget.minInkLength,
        }) ?? arrangeHomeColumns(text, budget.capacity, budget.maxColumns)
      )
    }

    const refresh = () => {
      if (scrollport.clientWidth <= 0) return
      const segments = poem.body_segments
      let chosen = segments

      if (!fits(segments)) {
        chosen = []
        for (let count = 1; count <= segments.length; count++) {
          const candidate = segments.slice(0, count)
          if (!fits(candidate)) break
          chosen = candidate
        }

        if (!chosen.length && segments[0]) {
          const first = segments[0]
          const sentenceEnds = [...first.matchAll(/[。！？!?]/gu)].map(
            (match) => match.index + match[0].length,
          )
          const punctuationEnds = [...first.matchAll(/[，、；;]/gu)].map(
            (match) => match.index + match[0].length,
          )
          for (const ends of [sentenceEnds, punctuationEnds]) {
            for (const end of ends) {
              const candidate = [first.slice(0, end)]
              if (!fits(candidate)) break
              chosen = candidate
            }
            if (chosen.length) break
          }
          if (!chosen.length) {
            let low = 1
            let high = first.length
            while (low <= high) {
              const middle = Math.floor((low + high) / 2)
              if (fits([first.slice(0, middle)])) {
                chosen = [first.slice(0, middle)]
                low = middle + 1
              } else {
                high = middle - 1
              }
            }
          }
        }
      }

      const next = chosen === segments ? null : chosen
      setPreviewSegments((previous) =>
        JSON.stringify(previous) === JSON.stringify(next) ? previous : next,
      )
    }

    refresh()
    const observer = new ResizeObserver(refresh)
    observer.observe(scrollport)
    const main = scrollport.closest('#home')
    const budgetObserver = new MutationObserver(refresh)
    if (main) budgetObserver.observe(main, { attributes: true, attributeFilter: ['style'] })
    void document.fonts.ready.then(() => {
      if (scrollport.isConnected) refresh()
    })
    return () => {
      observer.disconnect()
      budgetObserver.disconnect()
    }
  }, [poem, continuous])

  // 桌面与 iPad 横屏共用一份物理宽度预算：直接量当前题署与正文行距，
  // 不再让离屏 vertical-rl 克隆另算一次 Safari 的 max-content 宽度。
  useLayoutEffect(() => {
    if (continuous) return
    const port = poemScrollport.current
    const article = port?.querySelector<HTMLElement>('article')
    const header = article?.querySelector<HTMLElement>('header')
    const body = article?.querySelector<HTMLElement>('.poem-reader-body')
    const layout = port?.closest<HTMLElement>('[data-home-recommendation-layout]')
    const section = layout?.closest<HTMLElement>('section')
    const seal = layout?.querySelector<HTMLElement>('button')
    if (!article || !header || !body || !layout || !section || !seal) return

    const refresh = () => {
      const available =
        section.getBoundingClientRect().width -
        seal.getBoundingClientRect().width -
        (Number.parseFloat(getComputedStyle(layout).columnGap) || 0) -
        (Number.parseFloat(getComputedStyle(layout).getPropertyValue('--home-width-reserve')) || 0)
      if (available <= 0) return

      // 标题和作者列作为普通 Flex 子项，header 的真实物理宽度即题署预算。
      const headerWidth = header.getBoundingClientRect().width
      const bodyStyle = getComputedStyle(body)
      // 每个 .poem-reader-line 是一个独立的竖排列，横向步长就是实际 line-height。
      const advance = Number.parseFloat(bodyStyle.lineHeight)
      // CSS 的来源段间距比例是唯一权威值，测量不再另写常数。
      const sourceGapScale = Number.parseFloat(
        bodyStyle.getPropertyValue('--reader-source-gap-scale'),
      )
      const sourceGap = Number.parseFloat(bodyStyle.fontSize) * sourceGapScale
      if (!Number.isFinite(advance) || advance <= 0) return

      const widthOf = (segments: string[]) => {
        const lines = buildPoemLines(segments.join('\n\n'))
        return Math.ceil(
          headerWidth +
            lines.length * advance +
            lines.filter((line) => line.sourceGapBefore).length * sourceGap +
            2,
        )
      }
      const fits = (segments: string[]) => widthOf(segments) <= available
      const segments = poem.body_segments
      let chosen = segments

      if (!fits(segments)) {
        chosen = []
        for (const segment of segments) {
          const candidate = [...chosen, segment]
          if (!fits(candidate)) break
          chosen = candidate
        }

        // 只有第一片也无法完整容纳时，才退回到第一片内部按完整诗句截断。
        if (!chosen.length && segments[0]) {
          const first = segments[0]
          for (const line of buildPoemLines(first)) {
            const candidate = [first.slice(0, line.end)]
            if (!fits(candidate)) break
            chosen = candidate
          }
          // 极窄视口仍至少保留一句，不以 CSS 裁掉半列汉字。
          if (!chosen.length) {
            const firstLine = buildPoemLines(first)[0]
            if (firstLine) chosen = [firstLine.text]
          }
        }
      }

      const next = chosen === segments ? null : chosen
      setPreviewSegments((previous) =>
        JSON.stringify(previous) === JSON.stringify(next) ? previous : next,
      )
    }

    refresh()
    const observer = new ResizeObserver(refresh)
    observer.observe(section)
    observer.observe(header)
    window.addEventListener('resize', refresh)
    void document.fonts.ready.then(() => {
      if (article.isConnected) refresh()
    })
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', refresh)
    }
  }, [poem, continuous])

  const displayedSegments = previewSegments ?? poem.body_segments
  const desktopLines = continuous ? [] : buildPoemLines(displayedSegments.join('\n\n'))
  const desktopBookRuns = buildHomeBookTitleRuns(desktopLines.map((line) => line.text))
  const excerpted =
    previewSegments !== null &&
    (displayedSegments.length !== poem.body_segments.length ||
      displayedSegments.some((segment, index) => segment !== poem.body_segments[index]))

  return (
    <div
      data-recommendation-scrollport
      ref={poemScrollport}
      className={
        continuous
          ? 'min-w-0 flex-1 overflow-hidden lg:w-full lg:flex-none'
          : 'min-w-0 flex-1 lg:w-max lg:flex-none'
      }
    >
      <div className="flex w-full flex-row-reverse justify-center lg:w-max lg:min-w-0 lg:flex-row">
        <article
          dir="ltr"
          lang="zh-CN"
          className={`poem-reader home-featured-poem w-max shrink-0 font-serif ${!continuous ? 'lg:flex lg:flex-row-reverse lg:items-start' : ''}`}
          style={
            {
              writingMode: continuous ? 'vertical-rl' : 'horizontal-tb',
              textOrientation: 'mixed',
              '--home-classic-target-height': `${Math.round(208 + Math.max(0, poem.body_segments.join('').length - 36) * 7.5)}px`,
            } as CSSProperties
          }
        >
          {continuous ? (
            <header className="ml-3 lg:ml-2.5">
              {/* 手机首页沿用已封板的题署：标题、节选和作者在同一列。 */}
              <div className="flex flex-row items-center gap-4 mt-[var(--reader-poem-size)]">
                <h2 className="poem-reader-heading shrink-0 font-serif">
                  {poem.yusheng_title ?? poem.cipai ?? '词牌未核实'}
                </h2>
                {excerpted && (
                  <span className="shrink-0 font-serif text-2xl text-editorial-red">节选</span>
                )}
                <p className="poem-reader-author !mt-0 shrink-0 font-serif text-muted-foreground">
                  {poem.author ?? '作者未核实'}
                </p>
              </div>
              {poem.yusheng_title && poem.cipai && poem.author !== '贺铸' && (
                <p className="poem-reader-secondary-heading ml-3 text-muted-foreground lg:ml-2.5">
                  {poem.cipai}
                </p>
              )}
              {poem.title && (
                <p className="poem-reader-title ml-3 hidden whitespace-pre-line font-serif text-foreground/85 lg:ml-2.5">
                  {poem.title}
                </p>
              )}
            </header>
          ) : (
            // 桌面：最右题署列在标题后标示节选，作者独占下沉的次列。
            <header className="flex shrink-0 flex-row-reverse items-start gap-1.5 pl-2.5">
              <div className="flex flex-row items-center gap-3 [writing-mode:vertical-rl]">
                <h2 className="poem-reader-heading shrink-0 font-serif">
                  {poem.yusheng_title ?? poem.cipai ?? '词牌未核实'}
                </h2>
                {poem.yusheng_title && poem.cipai && poem.author !== '贺铸' && (
                  <p className="poem-reader-secondary-heading shrink-0 !text-base text-muted-foreground">
                    {poem.cipai}
                  </p>
                )}
                {poem.title && (
                  <p className="poem-reader-title !mt-0 shrink-0 whitespace-pre-line font-serif text-foreground/85">
                    {poem.title}
                  </p>
                )}
                {excerpted && (
                  <span className="home-featured-excerpt shrink-0 font-serif text-2xl font-normal text-editorial-red">
                    节选
                  </span>
                )}
              </div>
              <div className="pt-[calc(var(--reader-poem-size)+var(--home-author-optical-nudge))] [writing-mode:vertical-rl]">
                <p className="home-featured-author poem-reader-author !mt-0 shrink-0 font-serif text-muted-foreground">
                  {poem.author ?? '作者未核实'}
                </p>
              </div>
            </header>
          )}
          {/* 小序在首页手机端继续隐藏；桌面新题署暂不展示，阅读室保留全文。 */}
          {continuous &&
            poem.prefaces.map((preface, index) => (
              <p
                key={index}
                className={`ml-7 lg:ml-9 lg:mt-[var(--reader-poem-size)] max-h-[min(26rem,65dvh)] lg:max-h-[calc(11*var(--reader-poem-size)*1.12)] whitespace-pre-line font-serif text-[length:var(--reader-preface-size)] font-normal leading-[var(--reader-preface-line-height)] text-muted-foreground lg:[letter-spacing:0.08em] ${continuous ? 'hidden lg:block' : ''}`}
              >
                {preface}
              </p>
            ))}
          {continuous ? (
            <ContinuousPoemBody segments={displayedSegments} />
          ) : (
            <div className="poem-reader-body !mx-0 !w-max max-w-none text-foreground/90 lg:flex lg:flex-row-reverse lg:items-start lg:pt-[var(--reader-poem-size)]">
              {desktopLines.map((line, index) => (
                <span
                  key={line.start}
                  style={
                    {
                      '--home-stagger-index': Math.min(index, 8),
                      writingMode: 'vertical-rl',
                      textOrientation: 'mixed',
                      width: 'calc(var(--reader-poem-size) * var(--reader-poem-line-height))',
                    } as CSSProperties
                  }
                  className={
                    'poem-reader-line whitespace-nowrap' +
                    (line.sourceGapBefore ? ' poem-reader-source-gap' : '')
                  }
                >
                  <PunctuatedPoemText text={line.text} bookRuns={desktopBookRuns[index]} />
                </span>
              ))}
            </div>
          )}
        </article>
      </div>
    </div>
  )
}

/** 首页独有的书名线与标点淡化；《》保留在 DOM 中，但不占视觉字格。 */
function PunctuatedPoemText({
  text,
  bookRuns = buildHomeBookTitleRuns([text])[0],
}: {
  text: string
  bookRuns?: HomeBookTitleRun[]
}) {
  const punctuated = (value: string) =>
    buildPoemTextRuns(value).map((run, index) =>
      run.punctuation ? (
        <span key={index} className="poem-reader-punctuation">
          {run.text}
        </span>
      ) : (
        run.text
      ),
    )

  return bookRuns.map((part, index) => {
    if (part.kind === 'marker') {
      return (
        <span key={index} className="home-book-title-marker">
          {part.text}
        </span>
      )
    }
    if (part.kind === 'title') {
      return (
        <span key={index} className="home-book-title">
          <span className="home-book-title-text">{punctuated(part.text)}</span>
          <span className="home-book-title-line" aria-hidden="true" />
        </span>
      )
    }
    return <span key={index}>{punctuated(part.text)}</span>
  })
}

/** 节选与真实排版使用同一套列数/高度预算，避免宽度测量与断列结果分叉。 */
function getHomeMobileColumnBudget(body: HTMLElement, segments: string[]) {
  const scrollport = body.closest<HTMLElement>('[data-recommendation-scrollport]')
  const heading = body.closest('article')?.querySelector('header')
  const firstRow = heading?.querySelector('.flex')
  const main = body.closest<HTMLElement>('#home')
  if (!scrollport || !heading || !firstRow || !main) return null

  const computed = getComputedStyle(body)
  const fontSize = Number.parseFloat(computed.fontSize)
  const spacing = Number.parseFloat(computed.letterSpacing) || 0
  const lineHeight = Number.parseFloat(computed.lineHeight)
  const advance = fontSize + spacing
  const budget = Number.parseFloat(
    getComputedStyle(main).getPropertyValue('--home-classic-max-height'),
  )
  const maxHeight = Number.isFinite(budget) && budget > 0 ? budget : body.clientHeight
  const capacity = Math.floor((maxHeight - 3 + spacing) / advance)

  const headingInk = [...firstRow.children]
    .filter((child) => getComputedStyle(child).display !== 'none')
    .map((child) => child.getBoundingClientRect())
  const titleHeight = headingInk.length
    ? Math.max(...headingInk.map((rect) => rect.bottom)) -
      Math.min(...headingInk.map((rect) => rect.top))
    : 0
  const minInkLength = Math.floor(titleHeight / advance) + 1

  const headerMargin = Number.parseFloat(getComputedStyle(heading).marginLeft) || 0
  const available =
    scrollport.clientWidth - heading.getBoundingClientRect().width - headerMargin - 8
  const segmentGapBudget = Math.max(0, segments.length - 1) * fontSize * 0.5
  const physicalColumns = Math.floor((available - segmentGapBudget) / lineHeight)
  return {
    capacity,
    minInkLength,
    maxColumns: Math.min(HOME_MAX_BODY_COLUMNS, physicalColumns),
    maxHeight,
    advance,
  }
}

function ContinuousPoemBody({ segments }: { segments: string[] }) {
  const text = segments.join('\u3000')
  const mobileBody = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<{ columns: string[]; height: number } | null>(null)

  useLayoutEffect(() => {
    const body = mobileBody.current
    if (!body) return
    const main = body.closest<HTMLElement>('#home')

    const refresh = () => {
      if (window.matchMedia('(min-width: 1024px)').matches) return
      const budget = getHomeMobileColumnBudget(body, segments)
      if (!budget) return
      const { capacity, minInkLength, maxColumns, maxHeight, advance } = budget

      const chosen =
        arrangeHomeColumns(text, capacity, maxColumns, { minInkLength }) ??
        // 太矮的手机上物理空间可能不足，此时优先保证文字可显示。
        arrangeHomeColumns(text, capacity, maxColumns)
      if (!chosen) {
        setLayout(null)
        return
      }
      const longest = Math.max(...chosen.map((column) => Array.from(column).length))
      const height = Math.min(maxHeight, Math.ceil(longest * advance + 3))
      setLayout((previous) =>
        previous &&
        previous.height === height &&
        previous.columns.length === chosen.length &&
        previous.columns.every((column, index) => column === chosen[index])
          ? previous
          : { columns: chosen, height },
      )
    }

    refresh()
    const observer = new ResizeObserver(refresh)
    observer.observe(body)
    const mutation = new MutationObserver(refresh)
    if (main) mutation.observe(main, { attributes: true, attributeFilter: ['style'] })
    window.addEventListener('resize', refresh)
    void document.fonts.ready.then(() => {
      if (body.isConnected) refresh()
    })
    return () => {
      observer.disconnect()
      mutation.disconnect()
      window.removeEventListener('resize', refresh)
    }
  }, [text, segments])

  const columns = layout?.columns
  // 动态规划会省去行首的分片空格；用原文下标识别真正的新片起始行。
  const segmentStarts = new Set<number>()
  let segmentOffset = 0
  for (const [index, segment] of segments.entries()) {
    if (index > 0) {
      segmentOffset += 1
      segmentStarts.add(segmentOffset)
    }
    segmentOffset += Array.from(segment).length
  }
  let sourceOffset = 0
  const placedColumns = columns?.map((column, index) => {
    if (text[sourceOffset] === '\u3000' && !column.startsWith('\u3000')) sourceOffset += 1
    const beginsSegment = index > 0 && segmentStarts.has(sourceOffset)
    sourceOffset += Array.from(column).length
    return { text: column, beginsSegment }
  })
  const mobileBookRuns = buildHomeBookTitleRuns(
    placedColumns?.map((column) => column.text) ?? [text],
  )

  return (
    <>
      <div
        ref={mobileBody}
        className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 lg:hidden"
        style={layout ? { height: layout.height } : undefined}
      >
        {placedColumns ? (
          placedColumns.map((column, index) => (
            <span
              key={index}
              style={{ '--home-stagger-index': index } as CSSProperties}
              className={
                'home-classic-column' +
                (column.beginsSegment ? ' home-classic-column--new-segment' : '')
              }
            >
              <PunctuatedPoemText text={column.text} bookRuns={mobileBookRuns[index]} />
            </span>
          ))
        ) : (
          <PunctuatedPoemText text={text} bookRuns={mobileBookRuns[0]} />
        )}
      </div>
      <div className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 max-lg:hidden lg:pt-[var(--reader-poem-size)]">
        <PunctuatedPoemText text={text} bookRuns={buildHomeBookTitleRuns([text])[0]} />
      </div>
    </>
  )
}
