import test from 'node:test'
import assert from 'node:assert/strict'

import { buildHistory } from '../src/lib/chat-history.ts'

function doneTurn(id, question) {
  return {
    id,
    question,
    selection: null,
    answer: `answer-${id}`,
    status: 'done',
    error: null,
    usageLimitNotice: false,
    regenerating: false,
    regenerateError: null,
    regenerateLimitNotice: false,
    streamDraft: null,
  }
}

test('history limit is supplied by the server-facing caller, not duplicated in this module', () => {
  const turns = Array.from({ length: 8 }, (_, index) =>
    doneTurn(index + 1, `question-${index + 1}`),
  )

  const history = buildHistory(turns, 99, 3)

  assert.deepEqual(
    history.map((message) => message.content),
    ['question-6', 'answer-6', 'question-7', 'answer-7', 'question-8', 'answer-8'],
  )
})

test('zero history budget sends no previous turns', () => {
  assert.deepEqual(buildHistory([doneTurn(1, 'q')], 99, 0), [])
})
