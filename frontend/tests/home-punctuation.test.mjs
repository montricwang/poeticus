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

test('首页手机与桌面共用标点分段，保留原文与既有断列算法', () => {
  assert.match(display, /buildPoemTextRuns\(text\)/)
  assert.match(display, /<PunctuatedPoemText text=\{line.text\}/)
  assert.match(display, /<PunctuatedPoemText text=\{column.text\}/)
  assert.match(display, /<PunctuatedPoemText text=\{text\}/)
  assert.match(display, /arrangeHomeColumns\(text, capacity, maxColumns/)
})
