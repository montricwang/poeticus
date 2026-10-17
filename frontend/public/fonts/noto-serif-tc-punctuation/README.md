# Noto Serif TC punctuation subsets

这些字体文件取自 `@fontsource-variable/noto-serif-tc@5.3.1`，仅收录首页推荐所用的常见标点对应字体子集，遵循 `OFL.txt`（SIL Open Font License 1.1）。

`frontend/src/index.css` 通过 `@font-face` 的 `unicode-range` 只将这些字形用于标点，汉字仍由 Noto Serif SC 绘制。勿将整个 Noto Serif TC 无限制地设为首页正文字体，以免改变汉字字形。

首页推荐中的成对书名号 `《……》` **仅在展示时隐藏**，原始正文、阅读室和复制文本不改变；书名左侧显示连续波浪线。`frontend/public/decorations/book-title-wave-mask.svg` 提取自 Noto Serif TC 的 U+FE34：取 y=380–713 的一个周期（全字高约三周期），SVG 横向裁至 x=28–152，避免波峰被切平；以 CSS mask 平铺而非随书名字数拉伸。该衍生轮廓同样遵循此处的 OFL 许可。

书名线由 `frontend/src/index.css` 控制：默认颜色取 `--foreground`、淡化比例与标点共用 `--reader-punctuation-opacity`（目前 20%）；需要独立主题色或透明度时，可覆写 `--home-book-title-line-color`、`--home-book-title-line-opacity`，无需另绘 SVG。当前水平微调 `translateX(0.2em)` 是经过用户公网视觉验收的显示参数，Flex 的负外边距抵消装饰线宽度，**不得为调整书名线而撑大正文列距**。见 [PR #300](https://github.com/montricwang/poeticus/pull/300)、[PR #309](https://github.com/montricwang/poeticus/pull/309)。
