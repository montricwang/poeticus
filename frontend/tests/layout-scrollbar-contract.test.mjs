import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const companion = readFileSync(
  new URL('../src/components/desktop-companion-stage.tsx', import.meta.url),
  'utf8',
)
const divider = readFileSync(
  new URL('../src/components/editorial-divider.tsx', import.meta.url),
  'utf8',
)

test('桌面阅读区使用剩余视口高度，正文在本栏滚动', () => {
  assert.match(app, /flex h-dvh min-h-0 flex-col overflow-hidden/)
  assert.match(app, /flex min-h-0 w-full max-w-\[1600px\] flex-1 flex-col overflow-hidden/)
  assert.match(app, /grid h-full min-h-0 min-w-0/)
  assert.match(app, /poeticus-reader-scrollport flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto/)
  assert.doesNotMatch(app, /lg:h-auto lg:min-h-dvh lg:overflow-visible/)
})

test('伴读栏取父容器实际高度，并为输入框留出空间', () => {
  assert.match(companion, /observer\.observe\(stage\)/)
  assert.match(companion, /layout\.stageHeight - layout\.toolbarHeight - 8/)
  assert.match(companion, /--companion-panel-max-height/)
  assert.match(companion, /Math\.min\(layout\.stageHeight - layout\.contentHeight/)
})

test('延续生产版滚动条与分割线，不回退到浏览器默认外观', () => {
  assert.match(styles, /scrollbar-color: color-mix\(in oklab, var\(--foreground\) 6%, transparent\)/)
  assert.match(styles, /@supports selector\(::-webkit-scrollbar\)/)
  assert.match(styles, /border: 3px solid transparent/)
  assert.match(styles, /background-clip: padding-box/)
  assert.doesNotMatch(styles, /poeticus-auto-scrollbar/)
  assert.match(divider, /h-\[1\.5px\].*bg-border\/80/)
  assert.match(divider, /w-\[1\.5px\].*bg-border\/80/)
})
