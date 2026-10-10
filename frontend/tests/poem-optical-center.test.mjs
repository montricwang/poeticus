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

test('向左偏移只使用单侧剩余空间的一部分', () => {
  const rows = [80, 80, 80, 160, 160].map((width) => ({ start: 0, width }))
  const pure = opticalCenterOffset(rows, 160, 300)
  const biased = opticalCenterOffset(rows, 160, 300, 0.4)
  assert.ok(Math.abs(pure - biased - 28) < 1e-9)
  assert.equal(opticalCenterOffset(rows, 160, 160, 0.4), 0)
  assert.ok(Math.abs(opticalCenterOffset(rows, 160, 300, 2) - (pure - 70)) < 1e-9)
  assert.equal(opticalCenterOffset([{ start: 140, width: 20 }], 160, 300, 1), -70)
})

test('默认纯质心和无效偏移系数都保持原有算法', () => {
  const rows = [{ start: 0, width: 50 }]
  const expected = opticalCenterOffset(rows, 100, 200)
  assert.equal(opticalCenterOffset(rows, 100, 200, 0), expected)
  assert.equal(opticalCenterOffset(rows, 100, 200, Number.NaN), expected)
})
