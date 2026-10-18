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

  // 测量浏览器实际竖排宽度；整叠优先，容不下第一叠时才逐句截断。
  useLayoutEffect(() => {
    const scrollport = poemScrollport.current
    const article = scrollport?.querySelector('article')
    if (!scrollport || !article) return

    const probe = article.cloneNode(true) as HTMLElement
    probe.setAttribute('aria-hidden', 'true')
    Object.assign(probe.style, {
      position: 'fixed',
      left: '-10000px',
      top: '0',
      visibility: 'hidden',
      pointerEvents: 'none',
      width: 'max-content',
    })
    document.body.append(probe)
    const bodies = [...probe.querySelectorAll<HTMLElement>('.poem-reader-body')]
    // 测量节点不在 #home 下：不能丢失实际高度预算，也不能沿用克隆时的旧高度。
    for (const body of bodies) body.style.removeProperty('height')

    const measure = (segments: string[]) => {
      for (const body of bodies) fillProbeBody(body, segments, continuous)
      return probe.getBoundingClientRect().width
    }

    const fits = (segments: string[]) => {
      if (!continuous) {
        // 桌面预览的宽度预算属于「印章＋间距＋诗文」整体；与当前诗文宽度无关。
        // 不能再用会随已选片段缩小的 scrollport.clientWidth，否则会反复截短。
        const layout = scrollport.closest<HTMLElement>('[data-home-recommendation-layout]')
        const area = layout?.closest('section')
        const seal = layout?.querySelector('button')
        const gap = layout ? Number.parseFloat(getComputedStyle(layout).columnGap) || 0 : 0
        const available = (area?.clientWidth ?? 0) - (seal?.offsetWidth ?? 0) - gap - 4
        return available > 0 && measure(segments) <= available
      }
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
      // 随首页推荐槽位的高度同步；否则离屏克隆会退回 18rem，误判长词超宽。
      probe.style.setProperty(
        '--home-classic-max-height',
        getComputedStyle(scrollport).getPropertyValue('--home-classic-max-height'),
      )
      if (continuous && scrollport.clientWidth <= 0) return
      if (!continuous && !scrollport.closest('section')?.clientWidth) return
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
          // 桌面只截取完整的视觉诗句，不从一条句子中间截掉文字。
          if (!continuous) {
            for (const line of buildPoemLines(first)) {
              const candidate = [first.slice(0, line.end)]
              if (!fits(candidate)) break
              chosen = candidate
            }
          } else {
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
      }

      const next = chosen === segments ? null : chosen
      setPreviewSegments((previous) =>
        JSON.stringify(previous) === JSON.stringify(next) ? previous : next,
      )
    }

    refresh()
    const observer = new ResizeObserver(refresh)
    observer.observe(scrollport)
    // 桌面片段的宽度预算来自推荐区，而非随着片段缩短的正文容器。
    const recommendation = scrollport.closest('section')
    if (!continuous && recommendation) observer.observe(recommendation)
    const main = scrollport.closest('#home')
    const budgetObserver = new MutationObserver(refresh)
    if (main) budgetObserver.observe(main, { attributes: true, attributeFilter: ['style'] })
    void document.fonts.ready.then(() => {
      if (probe.isConnected) refresh()
    })
    return () => {
      observer.disconnect()
      budgetObserver.disconnect()
      probe.remove()
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
          : 'min-w-0 flex-1 overflow-hidden lg:w-max lg:max-w-full lg:flex-none'
      }
    >
      <div className="flex w-full flex-row-reverse justify-center lg:w-max lg:min-w-0 lg:flex-row">
        <article
          dir="ltr"
          lang="zh-CN"
          className={`poem-reader home-featured-poem w-max shrink-0 font-serif lg:[--reader-poem-line-height:1.5] lg:[--reader-poem-letter-spacing:0.12em] lg:[--reader-preface-size:0.875rem] lg:[--reader-preface-line-height:1.6] [--reader-author-size:1rem] lg:[--reader-author-size:1.125rem] lg:[--reader-title-size:1.25rem] ${continuous ? '[--reader-poem-line-height:1.5] [--reader-poem-letter-spacing:0.12em]' : ''}`}
          style={
            {
              writingMode: 'vertical-rl',
              textOrientation: 'mixed',
              '--home-classic-target-height': `${Math.round(208 + Math.max(0, poem.body_segments.join('').length - 36) * 7.5)}px`,
            } as CSSProperties
          }
        >
          <header className="ml-3 lg:ml-2.5">
            {/* 与横排阅读器一致：寓声为主标题，词牌另作辅助标题。 */}
            {/* 竖排 flex-row 沿纵向排列；词牌与作者共用一列，横向居中对齐。 */}
            <div
              className={`flex flex-row items-center gap-4 lg:ml-2.5 ${continuous ? 'mt-[var(--reader-poem-size)]' : ''}`}
            >
              <h2 className="poem-reader-heading shrink-0 font-serif">
                {poem.yusheng_title ?? poem.cipai ?? '词牌未核实'}
              </h2>
              {excerpted && (
                <span className="shrink-0 font-serif text-2xl text-[#AA381E]">节选</span>
              )}
              <p className="poem-reader-author !mt-0 shrink-0 font-serif text-muted-foreground">
                {poem.author ?? '作者未核实'}
              </p>
            </div>
            {poem.yusheng_title &&
              poem.cipai &&
              poem.id !== 'b3f3a428-ad69-4bef-90ff-797cc7dac849' && (
                <p className="poem-reader-secondary-heading ml-3 text-muted-foreground lg:ml-2.5">
                  {poem.cipai}
                </p>
              )}
            {poem.title && (
              <p
                className={`poem-reader-title ml-3 whitespace-pre-line font-serif text-foreground/85 lg:ml-2.5 lg:mt-[var(--reader-poem-size)] ${continuous ? 'hidden lg:block' : ''}`}
              >
                {poem.title}
              </p>
            )}
          </header>
          {/* 小序最多占约 11 个正文字高；1.12 对应正文 0.12em 的字距。 */}
          {poem.prefaces.map((preface, index) => (
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
            <div className="poem-reader-body !mx-0 !w-max max-w-none text-foreground/90 lg:pt-[var(--reader-poem-size)]">
              {desktopLines.map((line, index) => (
                <span
                  key={line.start}
                  style={{ '--home-stagger-index': Math.min(index, 8) } as CSSProperties}
                  className={
                    'poem-reader-line' + (line.sourceGapBefore ? ' poem-reader-source-gap' : '')
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

/** 离屏探针也隐藏书名号，避免把不可见的字格计入预览宽度。 */
function fillProbeBody(element: HTMLElement, segments: string[], continuous: boolean) {
  element.replaceChildren()
  const lines = continuous ? [] : buildPoemLines(segments.join('\n\n'))
  const chunks = continuous ? [segments.join('\u3000')] : lines.map((line) => line.text)
  const bookRuns = buildHomeBookTitleRuns(chunks)

  for (const [index, runs] of bookRuns.entries()) {
    const line = lines[index]
    const container = continuous ? element : document.createElement('span')
    if (line) {
      container.className =
        'poem-reader-line' + (line.sourceGapBefore ? ' poem-reader-source-gap' : '')
    }

    for (const part of runs) {
      const partElement = document.createElement('span')
      if (part.kind === 'marker') {
        partElement.className = 'home-book-title-marker'
        partElement.textContent = part.text
      } else {
        const textElement = part.kind === 'title' ? document.createElement('span') : partElement
        if (part.kind === 'title') {
          partElement.className = 'home-book-title'
          textElement.className = 'home-book-title-text'
        }
        for (const run of buildPoemTextRuns(part.text)) {
          const punctuation = document.createElement('span')
          if (run.punctuation) punctuation.className = 'poem-reader-punctuation'
          punctuation.textContent = run.text
          textElement.append(punctuation)
        }
        if (part.kind === 'title') {
          const lineElement = document.createElement('span')
          lineElement.className = 'home-book-title-line'
          lineElement.setAttribute('aria-hidden', 'true')
          partElement.append(textElement, lineElement)
        }
      }
      container.append(partElement)
    }
    if (!continuous) element.append(container)
  }
}
