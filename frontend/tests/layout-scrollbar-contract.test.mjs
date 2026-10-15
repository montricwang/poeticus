import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const desktopLayout = readFileSync(
  new URL('../src/components/desktop-layout.tsx', import.meta.url),
  'utf8',
)
const styles = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const companion = readFileSync(
  new URL('../src/components/reader-companion-layout.tsx', import.meta.url),
  'utf8',
)
const divider = readFileSync(
  new URL('../src/components/editorial-divider.tsx', import.meta.url),
  'utf8',
)
const readerPane = readFileSync(
  new URL('../src/components/reader-pane.tsx', import.meta.url),
  'utf8',
)
const companionPane = readFileSync(
  new URL('../src/components/companion-pane.tsx', import.meta.url),
  'utf8',
)

test('桌面阅读区使用剩余视口高度，正文在本栏滚动', () => {
  assert.match(app, /flex h-dvh min-h-0 flex-col overflow-hidden/)
  assert.match(
    desktopLayout,
    /flex min-h-0 w-full max-w-\[1600px\] flex-1 flex-col overflow-hidden/,
  )
  assert.match(companion, /grid h-full min-h-0 min-w-0/)
  assert.match(
    readerPane,
    /poeticus-reader-scrollport flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto/,
  )
  assert.doesNotMatch(app, /lg:h-auto lg:min-h-dvh lg:overflow-visible/)
})

test('阅读书页与底部分割线、导航共用阅读栏中心线', () => {
  // 阅读正文滚动区保留总共 8px 的滚动留白，但必须两侧对称。
  assert.match(readerPane, /overflow-y-auto overscroll-contain px-1/)
  assert.doesNotMatch(readerPane, /overscroll-contain pr-2/)
  assert.match(readerPane, /lg:max-w-\[27rem\] lg:px-4/)
  assert.match(
    readerPane,
    /<HorizontalEditorialDivider className="mb-3 hidden w-full lg:block" \/>/,
  )
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
  assert.match(styles, /--editorial-divider-thickness: 2px/)
  assert.match(companion, /gridTemplateColumns:/)
  assert.match(companion, /var\(--reader-column-share\)/)
  assert.match(companion, /var\(--editorial-divider-thickness\)/)
  assert.match(companion, /var\(--companion-column-share\)/)
  assert.doesNotMatch(companion, /grid-cols-\[1\.5px_/)
  assert.doesNotMatch(divider, /h-\[1\.5px\]|w-\[1\.5px\]/)
  assert.match(styles, /@supports selector\(::-webkit-scrollbar\)/)
  assert.match(styles, /border: 3px solid transparent/)
  assert.match(styles, /background-clip: padding-box/)
  assert.doesNotMatch(styles, /poeticus-auto-scrollbar/)
  assert.match(divider, /h-\[var\(--editorial-divider-thickness\)\].*bg-border\/80/)
  assert.match(divider, /w-\[var\(--editorial-divider-thickness\)\].*bg-border\/80/)
})

test('暖白与炭黑使用反色主操作，标点以主题前景色透明度弱化', () => {
  const light = styles.slice(styles.indexOf(':root {'), styles.indexOf('@theme inline'))
  const dark = styles.slice(styles.indexOf('.dark {'), styles.indexOf('@layer base'))
  assert.match(light, /--background: #faf9f6/)
  assert.match(light, /--foreground: #151411/)
  assert.match(light, /--primary: #151411/)
  assert.match(light, /--primary-foreground: #faf9f6/)
  assert.match(dark, /--background: #151411/)
  assert.match(dark, /--foreground: #faf9f6/)
  assert.match(dark, /--primary: #faf9f6/)
  assert.match(dark, /--primary-foreground: #151411/)
  assert.match(light, /--reader-punctuation-opacity: 20%/)
  assert.match(dark, /--reader-punctuation-opacity: 20%/)
  assert.match(
    styles,
    /color: color-mix\(in srgb, var\(--foreground\) var\(--reader-punctuation-opacity\), transparent\)/,
  )
  assert.doesNotMatch(styles, /--reader-punctuation-ink:/)
  assert.doesNotMatch(styles, /\.poem-reader-punctuation\s*\{\s*opacity:/)
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

test('小序与底部分割线共用 400px 行宽上限，自然换行且短序居中', () => {
  const reader = readFileSync(new URL('../src/components/poem-reader.tsx', import.meta.url), 'utf8')
  assert.match(reader, /poem-reader-preface whitespace-pre-line font-serif text-muted-foreground/)
  assert.match(
    styles,
    /\.poem-reader-preface \{[^}]*width: fit-content;[^}]*max-width: min\(100%, 25rem\);[^}]*margin-inline: auto;[^}]*text-align: left;/,
  )
  assert.match(styles, /--reader-preface-line-height: 1\.7;/)
  assert.doesNotMatch(styles, /\.poem-reader-preface \{[^}]*text-wrap: balance;/)
  assert.doesNotMatch(styles, /\.poem-reader-preface \{[^}]*text-indent:/)
  assert.doesNotMatch(styles, /\.poem-reader-preface-indented/)
  assert.doesNotMatch(reader, /function PoemPreface\(/)
})

test('桌面短词上下留白自动伸缩，书页整体偏上且不改变手机阅读', () => {
  const reader = readFileSync(new URL('../src/components/poem-reader.tsx', import.meta.url), 'utf8')
  assert.match(
    reader,
    /className="poem-reader-content bg-transparent lg:flex lg:flex-1 lg:flex-col"/,
  )
  assert.doesNotMatch(reader, /lg:justify-center/)
  assert.match(styles, /@media \(min-width: 64rem\) \{\s*\/\* 书页上下留白按剩余高度伸缩/)
  assert.match(styles, /\.poem-reader-content::before,\s*\.poem-reader-content::after \{/)
  assert.match(styles, /\.poem-reader-content::before \{\s*flex-grow: 0\.42/)
  assert.match(styles, /\.poem-reader-content::after \{\s*flex-grow: 0\.58/)
  assert.match(styles, /\.poem-reader-content > \.poem-reader-page \{\s*flex-shrink: 0/)
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
  assert.match(chat, /fillAvailableHeight \|\| turns\.length > 0/)
  assert.match(app, /renderDiscussionContent\(true\)/)
  assert.match(app, /renderDiscussionContent\(false\)/)
  assert.match(chatList, /transition-opacity/)
  assert.match(companion, /idle \? 0\.42 : 0\.5/)
})

test('输入区有初始宽度，文字增长只扩展输入与发送按钮', () => {
  const composer = readFileSync(
    new URL('../src/components/chat-composer.tsx', import.meta.url),
    'utf8',
  )
  assert.match(composer, /poeticus-composer-frame bg-transparent py-1/)
  assert.doesNotMatch(composer, /composerWidthForLines|composerWidth|--composer-content-width/)
  assert.match(styles, /\.poeticus-composer-frame \{\s*width: 100%;\s*max-width: 100%/)
  assert.doesNotMatch(styles, /--motion-companion-width|--motion-composer-width/)
  assert.match(divider, /h-\[var\(--editorial-divider-thickness\)\].*bg-border\/80/)
})

test('固定双栏的桌面目录与对话共用右侧工作区', () => {
  const catalog = readFileSync(
    new URL('../src/components/poem-catalog.tsx', import.meta.url),
    'utf8',
  )
  const responsive = readFileSync(
    new URL('../src/lib/responsive-layout.ts', import.meta.url),
    'utf8',
  )
  assert.match(styles, /--reading-stage-max-width: 1200px/)
  assert.match(styles, /--reader-column-share: 500fr/)
  assert.match(styles, /--companion-column-share: 650fr/)
  assert.match(desktopLayout, /max-w-\[var\(--reading-stage-max-width\)\]/)
  assert.match(desktopLayout, /<ReaderCompanionLayout/)
  assert.match(desktopLayout, /catalog=\{catalog.content\}/)
  assert.match(app, /discussion=\{renderDiscussionContent\(false\)\}/)
  assert.match(companion, /absolute inset-0 min-h-0 min-w-0 transition-opacity/)
  assert.match(companion, /aria-hidden=\{!catalogOpen\}/)
  assert.match(companion, /inert=\{!catalogOpen\}/)
  assert.ok(app.includes('const [catalogOpen, setCatalogOpen] = useState(false)'))
  assert.match(catalog, /embedded\?: boolean/)
  assert.ok(catalog.includes('embedded ?'))
  assert.doesNotMatch(app, /2xl:grid-cols-|2xl:transition-\[grid-template-columns\]/)
  assert.doesNotMatch(responsive, /PERSISTENT_CATALOG/)
  assert.match(responsive, /OVERLAY_CATALOG_MEDIA/)
})

test('视图短线独立成组件，引文关闭按钮仍紧邻文字', () => {
  const toolbar = readFileSync(
    new URL('../src/components/view-toolbar.tsx', import.meta.url),
    'utf8',
  )
  const quote = readFileSync(
    new URL('../src/components/quote-preview.tsx', import.meta.url),
    'utf8',
  )
  const viewDivider = readFileSync(
    new URL('../src/components/view-toolbar-divider.tsx', import.meta.url),
    'utf8',
  )
  assert.doesNotMatch(toolbar, /HorizontalEditorialDivider|ViewToolbarDivider/)
  assert.match(viewDivider, /<HorizontalEditorialDivider className="mb-3 w-\[7\.75rem\]"/)
  assert.doesNotMatch(viewDivider, /h-px|h-\[1\.5px\]/)
  assert.match(companionPane, /<ViewToolbar activeView=\{activeView\}/)
  assert.match(companionPane, /<ViewToolbarDivider \/>/)
  assert.doesNotMatch(app, /<ViewToolbarDivider|<ViewToolbar activeView=/)
  assert.match(quote, /inline-flex w-fit max-w-full/)
  assert.match(quote, /flex-\[0_1_auto\]/)
  assert.doesNotMatch(quote, /min-w-0 flex-1 overflow-y-auto/)
  assert.match(divider, /h-\[var\(--editorial-divider-thickness\)\].*bg-border\/80/)
})

test('阅读与伴读分割线由共同父 Pane 管理，不混入子组件', () => {
  const navigation = readFileSync(
    new URL('../src/components/reader-navigation.tsx', import.meta.url),
    'utf8',
  )
  const chat = readFileSync(new URL('../src/components/chat-panel.tsx', import.meta.url), 'utf8')
  assert.match(desktopLayout, /<ReaderPane/)
  assert.match(app, /<CompanionPane/)
  assert.match(app, /<ReaderNavigation[^>]*embedded/)
  assert.match(readerPane, /<HorizontalEditorialDivider/)
  assert.match(navigation, /<HorizontalEditorialDivider className="mb-3 w-full" \/>/)
  assert.match(
    readerPane,
    /<HorizontalEditorialDivider className="mb-3 hidden w-full lg:block" \/>/,
  )
  assert.match(navigation, /if \(embedded\) return navigation/)
  assert.match(navigation, /<footer className=/)
  const embeddedIndex = navigation.indexOf('if (embedded) return navigation')
  const footerIndex = navigation.indexOf('<footer className=')
  const mobileDividerIndex = navigation.indexOf('<HorizontalEditorialDivider')
  assert.ok(embeddedIndex < footerIndex && footerIndex < mobileDividerIndex)
  assert.match(companionPane, /<ViewToolbar/)
  assert.match(companionPane, /<ViewToolbarDivider/)
  assert.match(chat, /<HorizontalEditorialDivider className="w-full"/)
  assert.match(companion, /<VerticalEditorialDivider/)
  assert.match(styles, /--editorial-divider-thickness: 2px/)

  const scrollportIndex = readerPane.indexOf('ref={scrollRef}')
  const readerDividerIndex = readerPane.indexOf('<HorizontalEditorialDivider')
  const readerNavigationIndex = readerPane.indexOf('{navigation}', readerDividerIndex)
  assert.ok(scrollportIndex < readerDividerIndex && readerDividerIndex < readerNavigationIndex)
  assert.ok(companionPane.indexOf('<ViewToolbar ') < companionPane.indexOf('<ViewToolbarDivider'))
})

test('手机阅读导航保留提示，前后按钮各自贴近两端', () => {
  const navigation = readFileSync(
    new URL('../src/components/reader-navigation.tsx', import.meta.url),
    'utf8',
  )
  assert.match(navigation, /grid-cols-\[auto_minmax\(0,1fr\)_auto\]/)
  assert.match(navigation, /justify-self-start/)
  assert.match(navigation, /justify-self-end/)
  assert.match(navigation, /划选诗句，即可引用提问/)
  assert.doesNotMatch(navigation, /hidden whitespace-nowrap/)
  assert.match(navigation, /lg:max-w-\[27rem\]/)
  assert.match(navigation, /<HorizontalEditorialDivider className="mb-3 w-full" \/>/)
  assert.doesNotMatch(navigation, /hidden w-full lg:block/)
  assert.doesNotMatch(navigation, /mx-auto mt-6 w-full max-w-\[27rem\]/)
})

test('已有对话时输入区随讨论正文展开，换诗时不用宽度动画', () => {
  const composer = readFileSync(
    new URL('../src/components/chat-composer.tsx', import.meta.url),
    'utf8',
  )
  const chatPanel = readFileSync(
    new URL('../src/components/chat-panel.tsx', import.meta.url),
    'utf8',
  )
  const frame = composer.indexOf('poeticus-composer-frame bg-transparent py-1')
  const controls = composer.indexOf('className="flex w-full items-center justify-between px-2"')
  const button = composer.indexOf('aria-label="发送消息"')
  assert.ok(frame >= 0 && controls > frame && button > controls)
  assert.ok(chatPanel.includes("!fillAvailableHeight && 'w-full max-w-[37.5rem]'"))
  assert.doesNotMatch(chatPanel, /max-w-\[25rem\]|transition-\[max-width\]/)
  assert.doesNotMatch(composer, /poeticus-composer-expanded|poeticus-composer-switching/)
  assert.ok(composer.includes('className="rounded-md lg:w-20 lg:gap-1.5 lg:px-3"'))
})

test('竖线是独立 Grid 列，按右栏内容高度变化而不推动阅读区', () => {
  assert.match(companion, /<VerticalEditorialDivider/)
  assert.ok(companion.includes('const dividerHeight = catalogOpen'))
  assert.match(companion, /observer\.observe\(stage\)/)
  assert.match(companion, /observer\.observe\(content\)/)
  assert.match(companion, /marginTop: catalogOpen \? 0 : verticalOffset/)
  assert.ok(
    companion.includes(
      'minmax(0, var(--reader-column-share)) var(--editorial-divider-thickness) minmax(0, var(--companion-column-share))',
    ),
  )
  assert.match(companion, /gap-x-6/)
  const readerIndex = companion.indexOf('{reader}')
  const dividerIndex = companion.indexOf('<VerticalEditorialDivider')
  const stageIndex = companion.indexOf('<div ref={stageRef}')
  assert.ok(readerIndex >= 0 && readerIndex < dividerIndex && dividerIndex < stageIndex)
  assert.ok(desktopLayout.includes('catalogOpen={catalog.open}'))
})

test('桌面目录选择保留工作区、从右上角进入，并让交叉淡入淡出不卸载对话', () => {
  const catalog = readFileSync(
    new URL('../src/components/poem-catalog.tsx', import.meta.url),
    'utf8',
  )
  const mobileLayout = readFileSync(
    new URL('../src/components/mobile-layout.tsx', import.meta.url),
    'utf8',
  )
  assert.ok(desktopLayout.includes('import { PanelRight }'))
  assert.match(desktopLayout, /onClick=\{catalog.onToggle\}/)
  assert.match(desktopLayout, /size="sm"/)
  assert.match(desktopLayout, /<PanelRight className="size-4" aria-hidden="true" \/>\s*目录/)
  assert.match(mobileLayout, /<PanelLeft className="size-5" aria-hidden="true" \/>/)
  assert.ok(app.includes('if (!wideDiscussionLayout) closeCatalog()'))
  assert.ok(app.includes('if (!wideDiscussionLayout && catalogOpen) closeCatalog()'))
  assert.match(styles, /--motion-catalog-switch: 220ms/)
  assert.match(companion, /duration-\[var\(--motion-catalog-switch\)\]/)
  assert.match(companion, /aria-hidden=\{catalogOpen\}/)
  assert.match(companion, /inert=\{catalogOpen\}/)
  assert.match(catalog, /embedded \? 'flex h-14 items-center gap-3 ' : 'block py-3 '/)
  assert.match(catalog, /poeticus-catalog-title max-w-\[62%\]/)
  assert.match(styles, /font-family: 'Noto Sans SC Variable', 'Source Han Sans SC'/)
  assert.match(catalog, /Math\.floor\(list\.clientHeight \/ 56\)/)
  assert.match(catalog, /Math\.floor\(filters\.offset \/ limit\) \* limit/)
  assert.match(catalog, /aria-label="上一页"/)
  assert.match(catalog, /aria-label="下一页"/)
  assert.match(catalog, /<ChevronUp className="size-4" aria-hidden="true" \/>/)
  assert.equal((catalog.match(/<ChevronRight className=/g) ?? []).length, 1)
  assert.doesNotMatch(catalog, /ActionTooltip/)
  assert.match(catalog, /import \{ HorizontalEditorialDivider \}/)
  assert.equal((catalog.match(/<HorizontalEditorialDivider/g) ?? []).length, 2)
  assert.match(catalog, /max-w-130/)
  // Search and title size themselves; the bounded divider gap centers its line,
  // while the flexible list receives the remaining panel height.
  assert.match(catalog, /embedded \? 'px-3 pt-3' : 'border-b border-border\/50 p-3'/)
  assert.match(catalog, /h-\[clamp\(1rem,3vh,2\.5rem\)\] shrink-0 items-center justify-center/)
  assert.match(catalog, /poeticus-scrollport min-h-0 flex-1 overscroll-contain/)
  const dividerIndex = catalog.indexOf('h-[clamp(1rem,3vh,2.5rem)]')
  assert.ok(
    dividerIndex > catalog.indexOf('</form>') && dividerIndex < catalog.indexOf('ref={listRef}'),
  )
  assert.match(catalog, /title=\{embedded \? undefined : work\.incipit\}/)
})

test('手机与桌面外壳只组装视图，不各自维护业务状态', () => {
  const mobileLayout = readFileSync(
    new URL('../src/components/mobile-layout.tsx', import.meta.url),
    'utf8',
  )
  assert.match(app, /<MobileLayout/)
  assert.match(app, /<DesktopLayout/)
  assert.match(mobileLayout, /inert=\{discussion.open \|\| catalog.open\}/)
  assert.match(desktopLayout, /catalogOpen=\{catalog.open\}/)
  for (const shell of [mobileLayout, desktopLayout]) {
    assert.doesNotMatch(shell, /useState|useChatSession|usePoemDetail|usePoemCatalog/)
  }
})
