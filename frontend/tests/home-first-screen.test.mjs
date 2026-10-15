import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { featuredExcerpt } from '../src/lib/featured-poem.ts'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const home = readFileSync(new URL('../src/components/home-screen.tsx', import.meta.url), 'utf8')

test('short complete works remain intact, including their stanza break', () => {
  const poem = { body_segments: ['春风又绿江南岸。', '明月何时照我还？'] }
  assert.deepEqual(featuredExcerpt(poem), {
    text: '春风又绿江南岸。\n明月何时照我还？',
    isExcerpt: false,
  })
})

test('long work excerpt ends on a sentence instead of severing a verse', () => {
  const stanza = '山河岁月如流水。'.repeat(13)
  const result = featuredExcerpt({ body_segments: [stanza, '后篇不应出现在首页。'] })
  assert.equal(result.isExcerpt, true)
  assert.ok(result.text.endsWith('。'))
  assert.ok(result.text.length <= 82)
  assert.ok(!result.text.includes('后篇'))
})

test('homepage uses vertical writing and the existing catalog/reader owners', () => {
  assert.match(home, /writingMode: 'vertical-rl'/)
  assert.match(home, /maxLength=\{100\}/)
  assert.match(app, /<HomeScreen/)
  assert.match(app, /<DesktopLayout/)
  assert.match(app, /<MobileLayout/)
  assert.match(app, /onFiltersChange=\{updateCatalogFilters\}/)
  assert.match(app, /onSelect=\{openHomePoem\}/)
  assert.match(app, /window.location.hash === '#reader'/)
})
