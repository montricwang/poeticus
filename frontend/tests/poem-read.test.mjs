import test from "node:test";
import assert from "node:assert/strict";

import {
  poemIncipit,
  poemLabel,
  poemText,
  poemTitle,
} from "../src/data/poem-library.ts";
import { selectionForPython } from "../src/lib/selection-offset.ts";

test("API 正文段落按原有顺序拼接，且不推断上下片", () => {
  const work = {
    body_segments: ["第一段", "第二段\n原有换行", "第三段"],
  };
  assert.equal(poemText(work), "第一段\n\n第二段\n原有换行\n\n第三段");
});

test("目录词牌、词题、正文首句各归各位", () => {
  const summary = {
    cipai: "沁园春",
    yusheng_title: null,
    title: null,
    incipit: "瞬息浮生，薄命如斯",
  };
  assert.equal(poemTitle(summary), "沁园春");
  assert.equal(poemLabel(summary), "沁园春");
  assert.equal(poemIncipit(summary), "瞬息浮生");
});

test("有词题时第一行只包含词牌与题目", () => {
  const summary = {
    cipai: "念奴娇",
    yusheng_title: null,
    title: "赤壁怀古",
    incipit: "大江东去，浪淘尽",
  };
  assert.equal(poemLabel(summary), "念奴娇·赤壁怀古");
  assert.equal(poemIncipit(summary), "大江东去");
});

test("寓声作品显示寓声（原词牌）·词题，无题不多一个分隔符", () => {
  const summary = {
    cipai: "思越人",
    yusheng_title: "翦朝霞",
    title: "牡丹",
    incipit: "今日春光，往事如烟",
  };
  assert.equal(poemLabel(summary), "翦朝霞（思越人）·牡丹");
  assert.equal(poemLabel({ ...summary, title: null }), "翦朝霞（思越人）");
  assert.equal(poemLabel({ ...summary, cipai: null }), "翦朝霞·牡丹");
});

test("目录第二行在主要句读处截止，不依赖有无词题", () => {
  for (const [incipit, expected] of [
    ["梦草池南璧月堂。绿阴深蔽日，啼鹂黄。", "梦草池南璧月堂"],
    ["□波飞□□□□向。□□□□、□□□□在会", "□波飞□□□□向"],
    ["花影摇红，春日渐长。", "花影摇红"],
    ["谁知此意？唯有故人。", "谁知此意"],
    ["无言以对！一夜秋风。", "无言以对"],
    ["朝暮；千里之外。", "朝暮"],
    ["初遇。第二句。", "初遇"],
  ]) {
    assert.equal(poemIncipit({ incipit }), expected);
  }
});

test("没有标点时首句遵守 Unicode 字符上限", () => {
  assert.equal(poemIncipit({ incipit: "花".repeat(50) }), "花".repeat(28));
  assert.equal(poemIncipit({ incipit: "🌸".repeat(30) }), "🌸".repeat(28));
});

test("UTF-16 位置转换为 Python code point 位置", () => {
  const poem = "春𠮷\n\n秋月";
  assert.deepEqual(selectionForPython({
    text: "秋月",
    start: 5,
    end: 7,
  }, poem), {
    text: "秋月",
    start: 4,
    end: 6,
  });
});

test("不正确或过期的引用不得发送给 Python", () => {
  assert.equal(selectionForPython(null, "春秋"), null);
  assert.equal(selectionForPython({text:"月",start:0,end:1}, "春月"), null);
  assert.equal(selectionForPython({text:"月",start:1,end:7}, "春月"), null);
});
