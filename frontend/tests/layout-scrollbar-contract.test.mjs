import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const companion = readFileSync(
  new URL('../src/components/desktop-companion-stage.tsx', import.meta.url),
  'utf8',
)
const divider = readFileSync(
  new URL('../src/components/editorial-divider.tsx', import.meta.url),
  'utf8',
)

test('桌面阅读区使用剩余视口高度，正文在本栏滚动', () => {
  assert.match(app, /flex h-dvh min-h-0 flex-col overflow-hidden/)
  assert.match(app, /flex min-h-0 w-full max-w-\[1600px\] flex-1 flex-col overflow-hidden/)
  assert.match(app, /grid h-full min-h-0 min-w-0/)
  assert.match(
    app,
    /poeticus-reader-scrollport flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto/,
  )
  assert.doesNotMatch(app, /lg:h-auto lg:min-h-dvh lg:overflow-visible/)
})

test('伴读栏取父容器实际高度，并为输入框留出空间', () => {
  assert.match(companion, /observer\.observe\(stage\)/)
  assert.match(companion, /layout\.stageHeight - layout\.toolbarHeight - 8/)
  assert.match(companion, /--companion-panel-max-height/)
  assert.match(companion, /Math\.min\(layout\.stageHeight - layout\.contentHeight/)
})

test('延续生产版滚动条与分割线，不回退到浏览器默认外观', () => {
  assert.match(
    styles,
    /scrollbar-color: color-mix\(in oklab, var\(--foreground\) 6%, transparent\)/,
  )
  assert.match(styles, /@supports selector\(::-webkit-scrollbar\)/)
  assert.match(styles, /border: 3px solid transparent/)
  assert.match(styles, /background-clip: padding-box/)
  assert.doesNotMatch(styles, /poeticus-auto-scrollbar/)
  assert.match(divider, /h-\[1\.5px\].*bg-border\/80/)
  assert.match(divider, /w-\[1\.5px\].*bg-border\/80/)
})

test('自动隐藏只改变滑块可见性，不覆盖 Chrome 自定义尺寸', () => {
  const thumb = readFileSync(
    new URL('../src/hooks/use-auto-hide-scrollbars.ts', import.meta.url),
    'utf8',
  )
  assert.match(styles, /\.poeticus-scrollport::-webkit-scrollbar-thumb \{/)
  assert.match(styles, /\[data-scrolling='true'\]/)
  assert.match(styles, /@supports not selector\(::-webkit-scrollbar\)/)
  const autoHideStart = styles.indexOf('Only visibility changes while scrolling')
  const webkitBlock = styles.slice(
    styles.indexOf('@supports selector(::-webkit-scrollbar)', autoHideStart),
    styles.indexOf('@media (prefers-reduced-motion: reduce)', autoHideStart),
  )
  // Reintroducing a non-auto standard color in this block would suppress the
  // working Chromium ::-webkit-scrollbar thumb customization again.
  assert.doesNotMatch(webkitBlock, /scrollbar-color\s*:/)
  assert.doesNotMatch(webkitBlock, /scrollbar-width\s*:/)
  assert.match(thumb, /addEventListener\('scroll', onScroll, true\)/)
  assert.match(thumb, /removeEventListener\('scroll', onScroll, true\)/)
  assert.match(thumb, /--motion-scrollbar-idle-timeout/)
})

test('独立动画共用参数来源，历史消息与输入框不随整栏闪烁', () => {
  const composer = readFileSync(
    new URL('../src/components/chat-composer.tsx', import.meta.url),
    'utf8',
  )
  const chatPanel = readFileSync(
    new URL('../src/components/chat-panel.tsx', import.meta.url),
    'utf8',
  )
  const chatAnimation = readFileSync(
    new URL('../src/components/chat-animations.css', import.meta.url),
    'utf8',
  )
  const poemReader = readFileSync(
    new URL('../src/components/poem-reader.tsx', import.meta.url),
    'utf8',
  )
  assert.match(styles, /--motion-poem-swap: 360ms/)
  assert.match(styles, /--motion-quote-enter: 460ms/)
  assert.match(styles, /--motion-chat-history-resize: 500ms/)
  assert.match(styles, /--motion-message-enter: 380ms/)
  assert.match(styles, /--motion-chat-content-enter: 420ms/)
  assert.match(styles, /--motion-companion-reflow: 520ms/)
  assert.match(app, /motionDurationMs\('--motion-poem-swap'\)/)
  assert.match(composer, /<QuotePreview selected=\{selected\}/)
  const chatList = readFileSync(
    new URL('../src/components/chat-message-list.tsx', import.meta.url),
    'utf8',
  )
  assert.match(chatList, /swapPhase === 'steady'/)
  assert.match(chatList, /duration-\[var\(--motion-chat-content-enter\)\]/)
  assert.doesNotMatch(chatPanel, /history\.offsetWidth/)
  assert.match(chatList, /duration-\[var\(--motion-chat-history-resize\)\]/)
  assert.match(chatAnimation, /var\(--motion-message-enter\)/)
  assert.doesNotMatch(poemReader, /desktop-reading-stage-min-height/)
  assert.doesNotMatch(companion, /window\.innerHeight \* 0\.3/)
  assert.doesNotMatch(companion, /Math\.min\(608,/)
})

test('引文和消息列表都有退场状态，内容不会立即连同容器一起卸载', () => {
  const quote = readFileSync(
    new URL('../src/components/quote-preview.tsx', import.meta.url),
    'utf8',
  )
  const chat = readFileSync(new URL('../src/components/chat-panel.tsx', import.meta.url), 'utf8')
  const chatList = readFileSync(
    new URL('../src/components/chat-message-list.tsx', import.meta.url),
    'utf8',
  )
  assert.match(quote, /setExpanded\(false\)/)
  assert.match(quote, /setRendered\(selected\)/)
  assert.match(quote, /setRendered\(null\)/)
  assert.match(quote, /--motion-quote-enter/)
  assert.match(styles, /poeticus-quote-transition/)
  assert.match(styles, /height: 0/)
  assert.match(styles, /height var\(--motion-quote-enter\)/)
  assert.match(styles, /poeticus-quote-open/)
  assert.match(quote, /ResizeObserver\(measure\)/)
  assert.match(quote, /height: expanded \? contentHeight : 0/)
  assert.doesNotMatch(quote, /key=\{/)
  assert.match(chat, /<ChatMessageList/)
  assert.doesNotMatch(chat, /turns\.length > 0 \|\| !fillAvailableHeight/)
  assert.match(chat, /grid-rows-\[0fr\]/)
  assert.match(chat, /grid-rows-\[1fr\]/)
  assert.match(chat, /<HorizontalEditorialDivider className="w-full"/)
  assert.match(chatList, /transition-opacity/)
  assert.match(companion, /idle \? 0\.42 : 0\.5/)
})

test('输入区有初始宽度，文字增长只扩展输入与发送按钮', () => {
  const composer = readFileSync(
    new URL('../src/components/chat-composer.tsx', import.meta.url),
    'utf8',
  )
  assert.match(composer, /composerWidthForLines/)
  assert.match(composer, /poeticus-composer-frame/)
  assert.match(composer, /--composer-content-width/)
  assert.match(composer, /context\.measureText/)
  assert.match(styles, /--motion-composer-width: 320ms/)
  assert.match(styles, /--composer-min-width: 18rem/)
  assert.match(styles, /width: max\(var\(--composer-min-width\)/)
  assert.match(styles, /var\(--composer-content-width, 0px\)/)
  assert.match(styles, /max-width: 100%/)
  assert.doesNotMatch(styles, /max-width: min\(/)
  // Don't modify the shared divider to customize the editor.
  assert.match(divider, /h-\[1\.5px\].*bg-border\/80/)
})

test('阅读栏和伴读栏共用目录变化后的剩余空间', () => {
  assert.match(styles, /--reading-stage-max-width: 82rem/)
  assert.match(styles, /--reader-column-share: 0\.95fr/)
  assert.match(styles, /--companion-column-share: 1\.05fr/)
  assert.match(app, /max-w-\[var\(--reading-stage-max-width\)\]/)
  assert.match(app, /lg:grid-cols-\[minmax\(0,var\(--reader-column-share\)\)_minmax\(0,var\(--companion-column-share\)\)\]/)
  assert.doesNotMatch(styles, /\.poeticus-reading-columns/)
  assert.match(app, /2xl:grid-cols-\[320px_minmax\(0,1fr\)\]/)
  assert.match(app, /2xl:transition-\[grid-template-columns\]/)
  assert.match(app, /--motion-catalog-grid-resize/)
  assert.doesNotMatch(app, /max-w-\[74rem\]/)
  assert.doesNotMatch(app, /0\.85fr/)
  assert.doesNotMatch(app, /1\.15fr/)
})

test('工具栏自行拥有原有的短分割线，引文关闭按钮紧邻文字', () => {
  const toolbar = readFileSync(
    new URL('../src/components/view-toolbar.tsx', import.meta.url),
    'utf8',
  )
  const quote = readFileSync(
    new URL('../src/components/quote-preview.tsx', import.meta.url),
    'utf8',
  )
  assert.match(toolbar, /<HorizontalEditorialDivider/)
  assert.match(toolbar, /w-\[calc\(100%\+0\.75rem\)\]/)
  assert.doesNotMatch(app, /<ViewToolbar[\s\S]*?<HorizontalEditorialDivider className="w-\[calc\(/)
  assert.match(quote, /inline-flex w-fit max-w-full/)
  assert.match(quote, /flex-\[0_1_auto\]/)
  assert.doesNotMatch(quote, /min-w-0 flex-1 overflow-y-auto/)
  assert.match(styles, /--composer-min-width: min\(100%, max\(22rem, 72%\)\)/)
  assert.match(divider, /h-\[1\.5px\].*bg-border\/80/)
})
