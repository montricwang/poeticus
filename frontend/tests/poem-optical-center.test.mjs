import test from 'node:test'
import assert from 'node:assert/strict'

import { inkTextLength, opticalCenterOffset } from '../src/lib/poem-optical-center.ts'

test('行尾句读不计入墨迹宽度，行内标点保留', () => {
  assert.equal(inkTextLength('春风、秋雨，'), 5)
  assert.equal(inkTextLength('归来否？！”\n\n'), 3)
  assert.equal(inkTextLength('山海经》'), 4)
  assert.equal(inkTextLength('问君'), 2)
  assert.equal(inkTextLength('？！'), 0)
})

test('4、4、4、8、8 的质心介于中位数与最长行之间', () => {
  const rows = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  assert.ok(Math.abs(opticalCenterOffset(rows, 8, 20) - 6 / 7) < 1e-9)
})

test('容器狭窄时限制位移以保护完整诗行', () => {
  const rows = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  assert.equal(opticalCenterOffset(rows, 8, 9), 0.5)
  assert.equal(opticalCenterOffset(rows, 8, 8), 0)
})

test('行起点纳入计算，兼容未来的行缩进', () => {
  assert.equal(
    opticalCenterOffset(
      [
        { start: 0, width: 4 },
        { start: 4, width: 4 },
      ],
      8,
      20,
    ),
    0,
  )
})

test('没有有效文字或无效尺寸时回退传统居中', () => {
  assert.equal(opticalCenterOffset([], 10, 20), 0)
  assert.equal(opticalCenterOffset([{ start: 0, width: 0 }], 10, 20), 0)
  assert.equal(opticalCenterOffset([{ start: 0, width: 4 }], Number.NaN, 20), 0)
})

test('折中模式只应用质心修正的一定比例', () => {
  const rows = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  const full = opticalCenterOffset(rows, 8, 20)
  assert.ok(Math.abs(opticalCenterOffset(rows, 8, 20, 0.6) - full * 0.6) < 1e-9)
  assert.equal(opticalCenterOffset(rows, 8, 20, 0), 0)
  assert.equal(opticalCenterOffset(rows, 8, 20, 1), full)
})

test('折中模式不以容器余白为依据额外左移', () => {
  const rows = [{ start: 0, width: 8 }]
  assert.equal(opticalCenterOffset(rows, 8, 10, 0.6), 0)
  assert.equal(opticalCenterOffset(rows, 8, 100, 0.6), 0)
})

test('窄屏仍以完整诗行的可用空间限制位移', () => {
  const rows = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  assert.equal(opticalCenterOffset(rows, 8, 9, 0.6), 0.5)
  assert.equal(opticalCenterOffset(rows, 8, 8, 0.6), 0)
})

test('过界或无效折中系数不会产生不可预测偏移', () => {
  const rows = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  const pure = opticalCenterOffset(rows, 8, 20)
  assert.equal(opticalCenterOffset(rows, 8, 20, 2), pure)
  assert.equal(opticalCenterOffset(rows, 8, 20, -1), 0)
  assert.equal(opticalCenterOffset(rows, 8, 20, Number.NaN), pure)
})
