import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const display = readFileSync(
  new URL('../src/components/featured-poem-display.tsx', import.meta.url),
  'utf8',
)
const fontFamily = 'Poeticus Noto Serif TC Punctuation'
const fontFaces = [...css.matchAll(/@font-face\s*\{([^}]*)\}/g)]
  .map((match) => match[1])
  .filter((face) => face.includes(`font-family: '${fontFamily}'`))

function includesCodePoint(face, codePoint) {
  const ranges = face.match(/unicode-range:\s*([^;]+);/)?.[1] ?? ''
  return ranges.split(',').some((range) => {
    const [from, to = from] = range.trim().replace('U+', '').split('-')
    return codePoint >= Number.parseInt(from, 16) && codePoint <= Number.parseInt(to, 16)
  })
}

test('首页 TC 标点字体覆盖常见中式标点，但不覆盖正文汉字', () => {
  assert.equal(fontFaces.length, 9)
  for (const char of '，。！？、；：．“”‘’《》〈〉（）「」『』—…·') {
    assert.ok(
      fontFaces.some((face) => includesCodePoint(face, char.codePointAt(0))),
      char,
    )
  }
  for (const char of '春風词詩ABC') {
    assert.ok(!fontFaces.some((face) => includesCodePoint(face, char.codePointAt(0))), char)
  }
})

test('TC 标点字体文件全部存在且只应用在首页推荐正文', () => {
  for (const face of fontFaces) {
    const file = face.match(/src:\s*url\('([^']+)'\)/)?.[1]
    assert.ok(file, 'Font face must reference a local font')
    assert.ok(existsSync(new URL(`../public${file}`, import.meta.url)), file)
  }
  assert.match(
    css,
    /\.home-featured-poem \.poem-reader-body\s*\{[^}]*'Poeticus Noto Serif TC Punctuation', 'Noto Serif SC Variable'/,
  )
  assert.doesNotMatch(css, /\.poem-reader-punctuation\s*\{[^}]*font-family:/)
  assert.match(css, /--reader-punctuation-opacity: 20%/)
})

test('首页书名线使用 TC U+FE34 轮廓，颜色和透明度由 CSS 变量控制', () => {
  const asset = '/decorations/book-title-wave-mask.svg'
  assert.match(css, /--home-book-title-line-gap:\s*0\.02em/)
  assert.match(css, /\.home-featured-poem \.home-book-title\s*\{[^}]*display:\s*inline-flex;/)
  assert.match(css, /gap:\s*var\(--home-book-title-line-gap\)/)
  assert.match(css, /\.home-featured-poem \.home-book-title-line\s*\{[^}]*flex:\s*0 0 0\.1em;/)
  assert.match(css, /margin-block-end:\s*calc\(-0\.1em - var\(--home-book-title-line-gap\)\)/)
  assert.doesNotMatch(
    css,
    /\.home-featured-poem \.home-book-title-line\s*\{[^}]*position:\s*absolute/,
  )
  assert.match(
    css,
    /mask:\s*url\('\/decorations\/book-title-wave-mask\.svg'\) left top \/ 0\.1em 0\.333em repeat-y/,
  )
  assert.match(css, /--home-book-title-line-color, var\(--foreground\)/)
  assert.match(css, /--home-book-title-line-opacity, var\(--reader-punctuation-opacity\)/)
  assert.match(display, /className="home-book-title-line" aria-hidden="true"/)
  assert.match(display, /textElement\.className = 'home-book-title-text'/)
  assert.match(display, /lineElement\.className = 'home-book-title-line'/)
  const svg = readFileSync(new URL(`../public${asset}`, import.meta.url), 'utf8')
  assert.match(svg, /Noto Serif TC U\+FE34/)
  assert.match(svg, /viewBox="40 0 100 333"/)
  assert.match(svg, /fill="#000"/)
  assert.doesNotMatch(svg, /fill-opacity/)
  assert.match(svg, /translate\(0 713\) scale\(1 -1\)/)
})

test('首页手机与桌面共用标点分段，保留原文与既有断列算法', () => {
  assert.match(display, /buildPoemTextRuns\(/)
  assert.match(display, /<PunctuatedPoemText text=\{line.text\}/)
  assert.match(display, /<PunctuatedPoemText text=\{column.text\}/)
  assert.match(display, /<PunctuatedPoemText text=\{text\}/)
  assert.match(display, /arrangeHomeColumns\(text, capacity, maxColumns/)
})
