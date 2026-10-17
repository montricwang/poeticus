# Noto Serif TC punctuation subsets

这些字体文件取自 `@fontsource-variable/noto-serif-tc@5.3.1`，仅收录首页推荐所用的常见标点对应字体子集，遵循 `OFL.txt`（SIL Open Font License 1.1）。

`frontend/src/index.css` 通过 `@font-face` 的 `unicode-range` 只将这些字形用于标点，汉字仍由 Noto Serif SC 绘制。勿将整个 Noto Serif TC 无限制地设为首页正文字体，以免改变汉字字形。
