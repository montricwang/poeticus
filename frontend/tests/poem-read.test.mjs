import test from "node:test";
import assert from "node:assert/strict";

import { poemLabel, poemText, poemTitle } from "../src/data/poem-library.ts";
import { selectionForPython } from "../src/lib/selection-offset.ts";

test("API 正文段落按原有顺序拼接，且不推断上下片", () => {
  const work = {
    body_segments: ["第一段", "第二段\n原有换行", "第三段"],
  };
  assert.equal(poemText(work), "第一段\n\n第二段\n原有换行\n\n第三段");
});

test("无词题时目录补首句，不凭首句生成正式题目", () => {
  const summary = {
    cipai: "沁园春",
    title: null,
    incipit: "瞬息浮生，薄命如斯",
  };
  assert.equal(poemTitle(summary), "沁园春");
  assert.equal(poemLabel(summary), "沁园春 · 瞬息浮生，薄命如斯");
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
