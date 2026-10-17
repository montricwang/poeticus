import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import type { Poem } from '@/data/poem-library'
import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { fitHomeColumns } from '@/lib/home-preview-columns'

/** 作品文本只负责竖排与两种断列规则，不负责按钮和首页留白。 */
export function FeaturedPoemDisplay({ poem, continuous }: { poem: Poem; continuous: boolean }) {
  const poemScrollport = useRef<HTMLDivElement>(null)
  const [previewSegments, setPreviewSegments] = useState<string[] | null>(null)
  const [bodyExcerpted, setBodyExcerpted] = useState(false)

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

    const measure = (segments: string[]) => {
      for (const body of bodies) fillProbeBody(body, segments, continuous)
      return probe.getBoundingClientRect().width
    }

    const refresh = () => {
      const available = scrollport.clientWidth - 4
      if (available <= 0) return
      const segments = poem.body_segments
      let chosen = segments

      if (measure(segments) > available) {
        chosen = []
        for (let count = 1; count <= segments.length; count++) {
          const candidate = segments.slice(0, count)
          if (measure(candidate) > available) break
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
              if (measure(candidate) > available) break
              chosen = candidate
            }
            if (chosen.length) break
          }
          if (!chosen.length) {
            let low = 1
            let high = first.length
            while (low <= high) {
              const middle = Math.floor((low + high) / 2)
              if (measure([first.slice(0, middle)]) <= available) {
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
    document.fonts.ready.then(() => {
      if (probe.isConnected) refresh()
    })
    return () => {
      observer.disconnect()
      probe.remove()
    }
  }, [poem, continuous])

  const displayedSegments = previewSegments ?? poem.body_segments
  const excerpted =
    (continuous && bodyExcerpted) ||
    (previewSegments !== null &&
      (displayedSegments.length !== poem.body_segments.length ||
        displayedSegments.some((segment, index) => segment !== poem.body_segments[index])))

  // 样式一从最右列开始读；使用标准 LTR scrollLeft，避开 Safari 的 RTL 滚动差异。
  useLayoutEffect(() => {
    if (continuous) return
    const scrollport = poemScrollport.current
    if (!scrollport) return
    const showFirstColumn = () => {
      scrollport.scrollLeft = scrollport.scrollWidth - scrollport.clientWidth
      // 窄屏先让正文开头靠右显示；词牌仍保留在右侧，可以反向滑动查看。
      if (window.matchMedia('(max-width: 1023px)').matches) {
        const body = scrollport.querySelector('.poem-reader-body')
        if (body) {
          const bodyRight = body.getBoundingClientRect().right
          const viewportRight = scrollport.getBoundingClientRect().right
          scrollport.scrollLeft += bodyRight - viewportRight
        }
      }
    }
    showFirstColumn()
    const observer = new ResizeObserver(showFirstColumn)
    observer.observe(scrollport)
    if (scrollport.firstElementChild) observer.observe(scrollport.firstElementChild)
    return () => observer.disconnect()
  }, [continuous, poem])

  return (
    <div
      data-recommendation-scrollport
      ref={poemScrollport}
      className={
        continuous
          ? 'min-w-0 flex-1 overflow-hidden lg:w-full lg:flex-none'
          : 'poeticus-scrollport min-w-0 flex-1 overflow-x-auto lg:w-full lg:flex-none'
      }
    >
      <div className="flex w-full flex-row-reverse justify-center lg:w-max lg:min-w-full lg:flex-row">
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
            <ContinuousPoemBody segments={displayedSegments} onExcerptChange={setBodyExcerpted} />
          ) : (
            <div className="poem-reader-body !mx-0 !w-max max-w-none text-foreground/90 lg:pt-[var(--reader-poem-size)]">
              {buildPoemLines(displayedSegments.join('\n\n')).map((line) => (
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
  )
}

function ContinuousPoemBody({
  segments,
  onExcerptChange,
}: {
  segments: string[]
  onExcerptChange: (excerpted: boolean) => void
}) {
  const text = segments.join('\u3000')
  const mobileBody = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<{
    columns: string[]
    height: number
    excerpted: boolean
  } | null>(null)

  useLayoutEffect(() => {
    const body = mobileBody.current
    if (!body) return
    const main = body.closest<HTMLElement>('#home')

    const refresh = () => {
      if (window.matchMedia('(min-width: 1024px)').matches) return
      const scrollport = body.closest<HTMLElement>('[data-recommendation-scrollport]')
      const heading = body.closest('article')?.querySelector('header')
      const firstRow = heading?.querySelector('.flex')
      if (!scrollport || !heading || !firstRow || !main) return

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

      // 第一行的实际文字高度，不取会被正文撑长的 header 外盒。
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
      const maxColumns = Math.floor((available - segmentGapBudget) / lineHeight)

      const fitted = fitHomeColumns(text, capacity, maxColumns, { minInkLength })
      if (!fitted) {
        setLayout(null)
        onExcerptChange(false)
        return
      }
      const { columns: chosen, excerpted } = fitted
      onExcerptChange(excerpted)
      const longest = Math.max(...chosen.map((column) => Array.from(column).length))
      const height = Math.min(maxHeight, Math.ceil(longest * advance + 3))
      setLayout((previous) =>
        previous &&
        previous.height === height &&
        previous.excerpted === excerpted &&
        previous.columns.length === chosen.length &&
        previous.columns.every((column, index) => column === chosen[index])
          ? previous
          : { columns: chosen, height, excerpted },
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
  }, [text, segments, onExcerptChange])

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

  return (
    <>
      <div
        ref={mobileBody}
        className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 lg:hidden"
        style={layout ? { height: layout.height } : undefined}
      >
        {placedColumns
          ? placedColumns.map((column, index) => (
              <span
                key={index}
                className={
                  'home-classic-column' +
                  (column.beginsSegment ? ' home-classic-column--new-segment' : '')
                }
              >
                {column.text}
              </span>
            ))
          : text}
      </div>
      <div className="poem-reader-body home-classic-body !mx-0 !w-max max-w-none text-foreground/90 max-lg:hidden lg:pt-[var(--reader-poem-size)]">
        {text}
      </div>
    </>
  )
}

/** 离屏探针复用同一套字体、列高和标点样式，测到的宽度与正文一致。 */
function fillProbeBody(element: HTMLElement, segments: string[], continuous: boolean) {
  element.replaceChildren()
  if (!continuous) {
    for (const line of buildPoemLines(segments.join('\n\n'))) {
      const span = document.createElement('span')
      span.className = 'poem-reader-line' + (line.sourceGapBefore ? ' poem-reader-source-gap' : '')
      for (const run of buildPoemTextRuns(line.text)) {
        const runElement = document.createElement('span')
        if (run.punctuation) runElement.className = 'poem-reader-punctuation'
        runElement.textContent = run.text
        span.append(runElement)
      }
      element.append(span)
    }
    return
  }

  element.textContent = segments.join('\u3000')
}
