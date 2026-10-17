import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const app = source('../src/App.tsx')
const home = source('../src/components/home-screen.tsx')
const recommendation = source('../src/components/daily-recommendation.tsx')
const featuredDisplay = source('../src/components/featured-poem-display.tsx')
const featuredHook = source('../src/hooks/use-featured-poem.ts')
const seal = source('../src/components/read-poem-seal.tsx')
const search = source('../src/components/home-search.tsx')

test('home composes recommendation, divider and search independently', () => {
  assert.match(home, /<DailyRecommendation/)
  assert.match(home, /<HorizontalEditorialDivider/)
  assert.match(home, /<HomeSearch/)
  assert.ok(home.indexOf('<DailyRecommendation') < home.indexOf('<HorizontalEditorialDivider'))
  assert.ok(home.indexOf('<HorizontalEditorialDivider') < home.indexOf('<HomeSearch'))
})

test('home search uses editorial heading and an unboxed input with matching underline', () => {
  assert.match(search, /美要眇兮宜修/)
  assert.doesNotMatch(search, /在诗词中寻一处相逢|从现有馆藏中搜索，不必知道完整的词题。/)
  assert.match(
    search,
    /<HorizontalEditorialDivider className="home-search-intro-divider w-full peer-focus-within:bg-ring"/,
  )
  const formOpening = search.match(/<form[\s\S]*?>/)?.[0]
  assert.ok(formOpening)
  assert.doesNotMatch(formOpening, /rounded-xl|border-border|shadow-\[/)
})

test('homepage uses phrase layout on desktop and continuous layout on mobile', () => {
  assert.match(featuredDisplay, /writingMode: 'vertical-rl'/)
  assert.match(featuredDisplay, /buildPoemLines\(displayedSegments.join/)
  assert.match(featuredDisplay, /buildPoemTextRuns\(/)
  assert.match(featuredDisplay, /<PunctuatedPoemText text=\{line.text\}/)
  assert.match(featuredDisplay, /<PunctuatedPoemText text=\{column.text\}/)
  assert.match(recommendation, /matchMedia/)
  assert.doesNotMatch(recommendation, /setLayout|样式一|样式二/)
  assert.match(featuredDisplay, /home-classic-column/)
  assert.doesNotMatch(featuredDisplay, /home-compact-punctuation/)
  assert.match(recommendation, /<FeaturedPoemDisplay/)
  assert.match(recommendation, /<ReadPoemSeal/)
  assert.match(seal, /#AA381E/)
  assert.match(seal, /font-sans/)
  assert.match(seal, /hover:bg-\[#AA381E\]/)
})

test('homepage uses fixed recommendation without a preview debug selector', () => {
  assert.match(featuredHook, /fetchDailyPoem\(controller.signal\)/)
  assert.doesNotMatch(
    home,
    /选择首页测试词作|首页排版测试|PREVIEW_POEMS|onPreviewPoemChange|debugSampleId|HOME_DEBUG_POEMS|首页词牌排版调试/,
  )
  assert.doesNotMatch(app, /setPreviewPoemId|previewPoemId/)
})

test('homepage shares catalog and reader owners', () => {
  assert.match(search, /maxLength=\{100\}/)
  assert.match(app, /<HomeScreen/)
  assert.match(app, /<DesktopLayout/)
  assert.match(app, /<MobileLayout/)
  assert.match(app, /onFiltersChange=\{updateCatalogFilters\}/)
  assert.match(app, /onSelect=\{openHomePoem\}/)
  assert.match(app, /window.location.hash === '#reader'/)
})
