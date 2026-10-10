import test from 'node:test'
import assert from 'node:assert/strict'

import { composerWidthForLines } from '../src/lib/composer-width.ts'

const measure = (text) =>
  Array.from(text).reduce((total, character) => total + (character.codePointAt(0) > 255 ? 16 : 8), 0)

test('empty question reports only padding; CSS supplies the initial width', () => {
  assert.equal(composerWidthForLines('', measure), 32)
  assert.equal(composerWidthForLines('你好', measure), 64)
})

test('the longest line controls requested width, including manual line breaks', () => {
  assert.equal(composerWidthForLines('a'.repeat(45), measure), 392)
  assert.equal(composerWidthForLines('a'.repeat(120), measure), 992)
  assert.equal(composerWidthForLines('a'.repeat(45) + '\n短句', measure), 392)
  assert.equal(composerWidthForLines('短句\r\n' + '中'.repeat(25), measure), 432)
})

test('deleting text contracts the requested width; the CSS min remains intact', () => {
  assert.equal(composerWidthForLines('a'.repeat(80), measure), 672)
  assert.equal(composerWidthForLines('a'.repeat(10), measure), 112)
})
