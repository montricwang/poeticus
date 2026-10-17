# Noto Serif TC punctuation subsets

这些字体文件取自 `@fontsource-variable/noto-serif-tc@5.3.1`，收录首页推荐所用的常见标点字体子集及竖排书名线 `︴`（U+FE34）所在的 `11` 子集，遵循 `OFL.txt`（SIL Open Font License 1.1）。

`frontend/src/index.css` 使用 `@font-face` 的 `unicode-range`，让普通标点使用 TC 字形、书名线使用 TC 的 `︴` 字形，汉字仍由 Noto Serif SC 绘制。勿将整个 Noto Serif TC 无限制地设为首页正文字体，以免改变汉字字形。
