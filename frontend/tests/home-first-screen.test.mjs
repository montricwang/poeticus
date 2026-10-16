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

test('homepage uses phrase layout on desktop and continuous layout on mobile', () => {
  assert.match(featuredDisplay, /writingMode: 'vertical-rl'/)
  assert.match(featuredDisplay, /buildPoemLines\(displayedSegments.join/)
  assert.match(featuredDisplay, /buildPoemTextRuns\(line.text\)/)
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

test('home navigation switches between nine real preview poems', () => {
  for (const tune of [
    '杨柳枝',
    '菩萨蛮',
    '水调歌头',
    '如梦令',
    '戚氏',
    '八声甘州',
    '满庭芳',
    '兰陵王',
    '踏莎行',
  ]) {
    assert.ok(featuredHook.includes(`label: '${tune}'`))
  }
  assert.match(home, /选择首页测试词作/)
  assert.match(home, /onPreviewPoemChange\(candidate.id\)/)
  assert.match(app, /onPreviewPoemChange=\{setPreviewPoemId\}/)
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
