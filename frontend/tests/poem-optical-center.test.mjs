import test from 'node:test'
import assert from 'node:assert/strict'

import {
  adaptiveOpticalStrength,
  inkTextLength,
  opticalCenterOffset,
} from '../src/lib/poem-optical-center.ts'

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

test('动态修正比例由平均句宽和最长句宽共同决定', () => {
  const lengths = [4, 4, 4, 8, 8]
  assert.equal(
    adaptiveOpticalStrength(lengths.map((width) => ({ start: 0, width }))),
    0.7,
  )
  assert.equal(
    adaptiveOpticalStrength([4, 4, 4, 4, 8].map((width) => ({ start: 0, width }))),
    0.6,
  )
  assert.ok(
    Math.abs(
      adaptiveOpticalStrength([...Array(10).fill(4), 8].map((width) => ({ start: 0, width }))) -
        6 / 11,
    ) < 1e-9,
  )
})

test('全部等长时强度为一，但质心修正为零', () => {
  const measures = [8, 8, 8].map((width) => ({ start: 0, width }))
  const strength = adaptiveOpticalStrength(measures)
  assert.equal(strength, 1)
  assert.equal(opticalCenterOffset(measures, 8, 20, strength), 0)
})

test('空诗文、无效宽度不参与动态比例计算', () => {
  assert.equal(adaptiveOpticalStrength([]), 0)
  assert.equal(
    adaptiveOpticalStrength([
      { start: 0, width: 4 },
      { start: 0, width: 0 },
      { start: 0, width: Number.NaN },
      { start: -1, width: 9 },
    ]),
    1,
  )
})

test('根据句长分布插值得到的位移不超过纯质心位移', () => {
  const measures = [4, 4, 4, 8, 8].map((width) => ({ start: 0, width }))
  const strength = adaptiveOpticalStrength(measures)
  const pure = opticalCenterOffset(measures, 8, 20, 1)
  assert.ok(Math.abs(opticalCenterOffset(measures, 8, 20, strength) - pure * 0.7) < 1e-9)
})
