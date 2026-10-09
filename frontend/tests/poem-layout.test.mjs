import test from 'node:test'
import assert from 'node:assert/strict'

import { buildPoemLines, buildPoemTextRuns } from '../src/lib/poem-layout.ts'

test('分行保留原文及 UTF-16 位置', () => {
  const source = '春𠮷、夏雨，秋月。\n\n翠翘金缕双鸂鶒，水纹细起春池碧。'
  const lines = buildPoemLines(source)
  assert.equal(lines.map((line) => line.text).join(''), source)
  assert.equal(lines[0].text, '春𠮷、夏雨，')
  assert.equal(lines[1].text, '秋月。\n\n')
  assert.equal(lines[2].text, '翠翘金缕双鸂鶒，')
  assert.equal(lines[3].text, '水纹细起春池碧。')
  assert.equal(lines[2].sourceGapBefore, true)
  assert.equal(lines[2].start, '春𠮷、夏雨，秋月。\n\n'.length)
})

test('行末引号不丢失', () => {
  const source = '读《清平乐》，问：“归来否？！”犹见故人。'
  const lines = buildPoemLines(source)
  assert.equal(lines[0].text, '读《清平乐》，')
  assert.equal(lines[1].text, '问：“归来否？！”')
  assert.equal(lines[2].text, '犹见故人。')
  assert.equal(lines.map((line) => line.text).join(''), source)
})

test('句内顿号保持原样并可独立着色', () => {
  const source = '风、雨，花。'
  const runs = buildPoemTextRuns(source)
  assert.equal(runs.map((run) => run.text).join(''), source)
  assert.equal(
    runs
      .filter((run) => run.punctuation)
      .map((run) => run.text)
      .join(''),
    '、，。',
  )
})
