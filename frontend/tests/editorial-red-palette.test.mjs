import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('quotes, links, selection, and unread dots use the editorial red palette', () => {
  const components = [
    '../src/components/assistant-markdown.tsx',
    '../src/components/quote-preview.tsx',
    '../src/components/user-message.tsx',
    '../src/components/chat-message-list.tsx',
    '../src/components/mobile-layout.tsx',
    '../src/components/poem-body.tsx',
  ].map(read)

  assert.match(components[0], /border-editorial-red\/70/)
  assert.match(components[0], /text-editorial-red-readable/)
  assert.match(components[1], /border-editorial-red\/60/)
  assert.match(components[2], /border-editorial-red\/70/)
  assert.match(components[3], /bg-editorial-red-readable/)
  assert.match(components[4], /bg-editorial-red-readable/)
  assert.match(components[5], /selection:bg-editorial-red\/20/)
  assert.doesNotMatch(components.join('\n'), /(?:violet|purple|fuchsia)-/)
})

test('semantic errors use the same readable red while retaining error roles', () => {
  const css = read('../src/index.css')
  assert.match(css, /--editorial-red: #aa381e/)
  assert.match(css, /--editorial-red-readable: var\(--editorial-red\)/)
  assert.match(
    css,
    /--editorial-red-readable: color-mix\(in srgb, var\(--editorial-red\) 70%, white\)/,
  )
  assert.equal(css.match(/--destructive: var\(--editorial-red-readable\);/g)?.length, 2)
  assert.match(
    read('../src/components/assistant-message.tsx'),
    /role=\{notice \? 'status' : 'alert'\}/,
  )
})
