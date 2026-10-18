import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const css = source('../src/index.css')
const featured = source('../src/components/featured-poem-display.tsx')
const seal = source('../src/components/read-poem-seal.tsx')
const daily = source('../src/components/daily-recommendation.tsx')
const home = source('../src/components/home-screen.tsx')

test('home optical adjustments and width budget have one CSS owner', () => {
  assert.match(css, /--home-author-optical-nudge:\s*2px/)
  assert.match(featured, /var\(--home-author-optical-nudge\)/)
  assert.match(css, /--home-width-reserve:\s*8px/)
  assert.match(featured, /getPropertyValue\('--home-width-reserve'\)/)
  assert.match(daily, /home-recommendation-layout/)
  assert.doesNotMatch(featured, /const sourceGap = [^\n]*\* 0\.9/)
})

test('source paragraph spacing uses one ratio for CSS and JS', () => {
  assert.match(css, /--reader-source-gap-scale:\s*0\.9/)
  assert.match(css, /margin-block-start:\s*calc\(var\(--reader-source-gap-scale\) \* 1em\)/)
  assert.match(featured, /getPropertyValue\('--reader-source-gap-scale'\)/)
})

test('editorial accent and seal spacing are named tokens, not duplicated hex literals', () => {
  assert.match(css, /--editorial-red-base:\s*#aa381e/i)
  assert.match(css, /--editorial-red:\s*var\(--editorial-red-base\)/)
  assert.match(
    css,
    /--editorial-red:\s*color-mix\(in srgb, var\(--editorial-red-base\) 75%, transparent\)/,
  )
  assert.match(css, /--color-editorial-red:\s*var\(--editorial-red\)/)
  assert.match(css, /--home-seal-glyph-gap:\s*0\.18em/)
  assert.match(seal, /home-read-seal-glyphs/)
  assert.match(seal, /border-editorial-red/)
  assert.match(featured, /text-editorial-red/)
  assert.match(seal, /text-editorial-red/)
  assert.doesNotMatch([seal, featured, home].join('\n'), /#aa381e/i)
})
