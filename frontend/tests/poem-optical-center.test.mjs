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
