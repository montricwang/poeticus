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
  assert.equal(poemLabel(summary), "沁园春 · 瞬息浮生");
});


test("有词题时只使用词牌与词题，不拼入 incipit", () => {
  const summary = {
    cipai: "思越人",
    title: "牡丹",
    incipit: "今日春光，往事如烟",
  };
  assert.equal(poemLabel(summary), "思越人·牡丹");
});

test("目录首句在逗号、句号等主要句读处截止", () => {
  for (const [incipit, expected] of [
    ["梦草池南璧月堂。绿阴深蔽日，啼鹂黄。", "梦草池南璧月堂"],
    ["□波飞□□□□向。□□□□、□□□□在会", "□波飞□□□□向"],
    ["花影摇红，春日渐长。", "花影摇红"],
    ["谁知此意？唯有故人。", "谁知此意"],
    ["无言以对！一夜秋风。", "无言以对"],
    ["朝暮；千里之外。", "朝暮"],
    ["初遇。第二句。", "初遇"],
  ]) {
    assert.equal(
      poemLabel({ cipai: "小重山", title: null, incipit }),
      `小重山 · ${expected}`,
    );
  }
});

test("无主要句读时目录首句有兜底长度限制", () => {
  const summary = { cipai: "浣溪沙", title: null, incipit: "花".repeat(50) };
  assert.equal(poemLabel(summary), "浣溪沙 · " + "花".repeat(18));
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
