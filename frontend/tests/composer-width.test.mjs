import test from 'node:test'
import assert from 'node:assert/strict'

import { composerWidthForLines } from '../src/lib/composer-width.ts'

const measure = (text) =>
  Array.from(text).reduce((total, character) => total + (character.codePointAt(0) > 255 ? 16 : 8), 0)

test('empty question starts compact rather than filling the companion', () => {
  assert.equal(composerWidthForLines('', measure), 288)
  assert.equal(composerWidthForLines('你好', measure), 288)
})

test('input expands with the longest line, then caps at its editorial maximum', () => {
  assert.equal(composerWidthForLines('a'.repeat(45), measure), 392)
  assert.equal(composerWidthForLines('a'.repeat(120), measure), 608)
  assert.equal(composerWidthForLines('a'.repeat(45) + '\n短句', measure), 392)
  assert.equal(composerWidthForLines('短句\r\n' + '中'.repeat(25), measure), 432)
})

test('deleting text contracts back to the initial width', () => {
  assert.equal(composerWidthForLines('a'.repeat(80), measure), 608)
  assert.equal(composerWidthForLines('a'.repeat(10), measure), 288)
})
