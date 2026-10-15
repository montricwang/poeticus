import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const app = source('../src/App.tsx')
const home = source('../src/components/home-screen.tsx')
const recommendation = source('../src/components/daily-recommendation.tsx')
const search = source('../src/components/home-search.tsx')

test('home composes recommendation, divider and search independently', () => {
  assert.match(home, /<DailyRecommendation/)
  assert.match(home, /<HorizontalEditorialDivider/)
  assert.match(home, /<HomeSearch/)
  assert.ok(home.indexOf('<DailyRecommendation') < home.indexOf('<HorizontalEditorialDivider'))
  assert.ok(home.indexOf('<HorizontalEditorialDivider') < home.indexOf('<HomeSearch'))
})

test('homepage preserves classic and phrase layouts without changing the original poem', () => {
  assert.match(recommendation, /writingMode: 'vertical-rl'/)
  assert.match(recommendation, /buildPoemLines\(poemText\(poem\)\)/)
  assert.match(recommendation, /buildPoemTextRuns\(line.text\)/)
  assert.match(recommendation, /setLayout\('phrases'\)/)
  assert.match(recommendation, /setLayout\('continuous'\)/)
  assert.match(recommendation, /poem.body_segments.join\('　　'\)/)
  assert.match(recommendation, /mobilePreview\(poem.body_segments\)/)
  assert.doesNotMatch(recommendation, /featuredExcerpt|visibleLines/)
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
