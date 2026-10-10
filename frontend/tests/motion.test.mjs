import test from 'node:test'
import assert from 'node:assert/strict'

import { motionDurationMs } from '../src/lib/motion.ts'

test('JavaScript uses the same duration token as CSS', () => {
  const oldDocument = globalThis.document
  const oldComputed = globalThis.getComputedStyle
  globalThis.document = { documentElement: {} }
  globalThis.getComputedStyle = () => ({
    getPropertyValue(token) {
      const tokens = {
        '--motion-poem-swap': '360ms',
        '--motion-chat-history-resize': '0.5s',
        '--motion-invalid': 'unknown',
      }
      return tokens[token] ?? ''
    },
  })

  try {
    assert.equal(motionDurationMs('--motion-poem-swap'), 360)
    assert.equal(motionDurationMs('--motion-chat-history-resize'), 500)
    assert.equal(motionDurationMs('--motion-invalid'), 0)
    assert.equal(motionDurationMs('--motion-missing'), 0)
  } finally {
    globalThis.document = oldDocument
    globalThis.getComputedStyle = oldComputed
  }
})
