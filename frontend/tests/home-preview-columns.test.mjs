import test from 'node:test'
import assert from 'node:assert/strict'

import { arrangeHomeColumns, inkCharacterCount } from '../src/lib/home-preview-columns.ts'

test('杨柳枝由通用断行评分自然选出四行，各为七字加标点', () => {
  const text = '宜春苑外最长条，闲袅春风伴舞腰。正是玉人肠绝处，一渠春水赤栏桥。'
  assert.deepEqual(arrangeHomeColumns(text, 8, 7), [
    '宜春苑外最长条，',
    '闲袅春风伴舞腰。',
    '正是玉人肠绝处，',
    '一渠春水赤栏桥。',
  ])
})

test('如梦令保持叠句，不把「那得」割开', () => {
  const text = '郊外绿阴千里，掩映红裙十队。惜别语方长，车马催人速去。偷泪，偷泪，那得分身应你？'
  const columns = arrangeHomeColumns(text, 9, 7)
  assert.ok(columns)
  assert.deepEqual(columns.slice(-2), ['偷泪，偷泪，', '那得分身应你？'])
  assert.equal(columns.join(''), text)
})

test('菩萨蛮在每行可容纳十三字符时自然排成五行', () => {
  const text =
    '小山重叠金明灭，鬓云欲度香腮雪。懒起画蛾眉，弄妆梳洗迟。　照花前后镜，花面交相映。新贴绣罗襦，双双金鹧鸪。'
  const columns = arrangeHomeColumns(text, 13, 7)
  assert.deepEqual(columns, [
    '小山重叠金明灭，',
    '鬓云欲度香腮雪。',
    '懒起画蛾眉，弄妆梳洗迟。',
    '照花前后镜，花面交相映。',
    '新贴绣罗襦，双双金鹧鸪。',
  ])
  assert.equal(columns.join(''), text.replace('　', ''))
})

test('标题长度约束：杨柳枝四行过短，合为两行', () => {
  const text = '宜春苑外最长条，闲袅春风伴舞腰。正是玉人肠绝处，一渠春水赤栏桥。'
  const columns = arrangeHomeColumns(text, 19, 6, {
    minInkLength: 9,
  })
  assert.deepEqual(columns, [
    '宜春苑外最长条，闲袅春风伴舞腰。',
    '正是玉人肠绝处，一渠春水赤栏桥。',
  ])
  assert.ok(Math.max(...columns.map(inkCharacterCount)) > 9)
})

test('标题长度约束：如梦令排成三行', () => {
  const text = '郊外绿阴千里，掩映红裙十队。惜别语方长，车马催人速去。偷泪，偷泪，那得分身应你？'
  const columns = arrangeHomeColumns(text, 19, 6, {
    minInkLength: 9,
  })
  assert.equal(columns?.length, 3)
  assert.equal(columns?.join(''), text)
})

test('行尾标点不计入墨迹高度', () => {
  assert.equal(inkCharacterCount('一渠春水赤栏桥。'), 7)
  assert.equal(inkCharacterCount('小山重叠金明灭，'), 7)
  assert.equal(inkCharacterCount('梦里江南，'), 4)
})

test('惩罚行首残字：不把「腮雪。」拆成「腮｜雪。」', () => {
  const text =
    '小山重叠金明灭，鬓云欲度香腮雪。懒起画蛾眉，弄妆梳洗迟。　照花前后镜，花面交相映。新贴绣罗襦，双双金鹧鸪。'
  const lines = arrangeHomeColumns(text, 14, 7)
  assert.ok(lines)
  assert.equal(lines.length, 5)
  assert.ok(lines.every((line) => !line.startsWith('雪。')))
  assert.equal(lines.join(''), text.replace('　', ''))
})

test('惩罚行尾孤字：不把「残照」拆成「残｜照」', () => {
  const text =
    '对潇潇暮雨洒江天，一番洗清秋。渐霜风凄紧，关河冷落，残照当楼。是处红衰翠减，苒苒物华休。惟有长江水，无语东流。'
  const lines = arrangeHomeColumns(text, 14, 7)
  assert.ok(lines)
  assert.equal(lines.length, 5)
  assert.ok(lines.every((line) => !line.endsWith('，残')))
  assert.equal(lines.join(''), text)
})

test('空间实在不够时，孤字惩罚仍允许退让，而不是不显示诗文', () => {
  const text =
    '小山重叠金明灭，鬓云欲度香腮雪。懒起画蛾眉，弄妆梳洗迟。　照花前后镜，花面交相映。新贴绣罗襦，双双金鹧鸪。'
  const lines = arrangeHomeColumns(text, 14, 4)
  assert.ok(lines)
  assert.equal(lines.length, 4)
  assert.equal(lines.join(''), text.replace('　', ''))
})
