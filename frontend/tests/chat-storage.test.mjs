import test from 'node:test'
import assert from 'node:assert/strict'

import { createConversationId } from '../src/lib/chat-storage.ts'

function withWindowCrypto(crypto, run) {
  const previousWindow = globalThis.window
  globalThis.window = { crypto }

  try {
    run()
  } finally {
    if (previousWindow === undefined) {
      delete globalThis.window
    } else {
      globalThis.window = previousWindow
    }
  }
}

test('conversation ID prefers native randomUUID when available', () => {
  withWindowCrypto(
    {
      randomUUID() {
        return '11111111-2222-4333-8444-555555555555'
      },
    },
    () => {
      assert.equal(createConversationId(), '11111111-2222-4333-8444-555555555555')
    },
  )
})

test('conversation ID falls back to getRandomValues when randomUUID is unavailable', () => {
  withWindowCrypto(
    {
      getRandomValues(bytes) {
        for (let index = 0; index < bytes.length; index += 1) {
          bytes[index] = index
        }
        return bytes
      },
    },
    () => {
      const id = createConversationId()

      assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
      assert.equal(id, '00010203-0405-4607-8809-0a0b0c0d0e0f')
    },
  )
})
