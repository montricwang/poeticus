# 《唐宋词鉴赏辞典》1505 篇批评方法统计概览

数据：`critic_methods_reviewed_v2_1505.jsonl`；SHA-256：`f70c8b1e66a27fe5c2d2d4339e12865983577316783a700e98944853a692ca02`。

共 1505 篇、7927 条方法分析（平均 5.27 条/篇）、14 种方法标签、227 种评论者署名字符串。

## 方法分布

| 方法标签 | 涉及篇数 | 占 1505 篇比例 | 方法条数 |
| --- | ---: | ---: | ---: |
| `STRUCTURE` | 1179 | 78.3% | 1196 |
| `TEXT_WORD` | 996 | 66.2% | 1037 |
| `INTERTEXT` | 904 | 60.1% | 949 |
| `CONTEXT` | 692 | 46.0% | 707 |
| `DEBATE` | 614 | 40.8% | 634 |
| `IMAGE` | 548 | 36.4% | 560 |
| `AESTHETICS` | 536 | 35.6% | 542 |
| `ALLUSION` | 525 | 34.9% | 539 |
| `NARRATIVE` | 463 | 30.8% | 470 |
| `TIME_SPACE` | 400 | 26.6% | 401 |
| `HISTORY` | 291 | 19.3% | 296 |
| `ALLEGORY` | 227 | 15.1% | 228 |
| `COUNTERFACTUAL` | 200 | 13.3% | 200 |
| `PROSODY` | 167 | 11.1% | 168 |

同一篇可以使用多个标签；涉及篇数对同篇同标签去重，方法条数不去重，比例不能相加。

## 评论者分布

43 种署名至少出现 10 篇，48 种署名只出现 1 篇；无署名 0 篇。

| 评论者署名 | 篇数 | 最常见的 3 类方法（涉及篇数） |
| --- | ---: | --- |
| 周啸天 | 69 | `STRUCTURE` 51、`TEXT_WORD` 45、`INTERTEXT` 37 |
| 徐培均 | 66 | `TEXT_WORD` 50、`INTERTEXT` 46、`STRUCTURE` 45 |
| 邓小军 | 55 | `STRUCTURE` 37、`INTERTEXT` 35、`TEXT_WORD` 35 |
| 陈永正 | 46 | `INTERTEXT` 35、`TEXT_WORD` 35、`STRUCTURE` 34 |
| 陈祥耀 | 40 | `STRUCTURE` 30、`TEXT_WORD` 28、`INTERTEXT` 27 |
| 刘学锴 | 36 | `STRUCTURE` 30、`TEXT_WORD` 26、`INTERTEXT` 20 |
| 李济阻 | 35 | `STRUCTURE` 28、`TEXT_WORD` 25、`INTERTEXT` 19 |
| 邱鸣皋 | 34 | `STRUCTURE` 29、`TEXT_WORD` 26、`CONTEXT` 17 |
| 谢桃坊 | 32 | `STRUCTURE` 26、`TEXT_WORD` 24、`INTERTEXT` 20 |
| 钟振振 | 31 | `STRUCTURE` 24、`INTERTEXT` 23、`DEBATE` 18 |
| 高 原 | 25 | `STRUCTURE` 19、`ALLUSION` 14、`IMAGE` 12 |
| 潘君昭 | 24 | `TEXT_WORD` 17、`INTERTEXT` 16、`STRUCTURE` 15 |
| 杨海明 | 23 | `STRUCTURE` 21、`TEXT_WORD` 19、`INTERTEXT` 17 |
| 周汝昌 | 22 | `TEXT_WORD` 18、`DEBATE` 14、`STRUCTURE` 14 |
| 李廷先 | 22 | `STRUCTURE` 17、`CONTEXT` 15、`DEBATE` 14 |
| 汤华泉 | 21 | `STRUCTURE` 18、`INTERTEXT` 17、`TEXT_WORD` 14 |
| 羊春秋 | 20 | `STRUCTURE` 15、`TEXT_WORD` 14、`INTERTEXT` 12 |
| 王双启 | 19 | `STRUCTURE` 16、`TEXT_WORD` 16、`INTERTEXT` 12 |
| 艾治平 | 19 | `TEXT_WORD` 15、`INTERTEXT` 13、`STRUCTURE` 13 |
| 陈长明 | 17 | `STRUCTURE` 14、`ALLUSION` 11、`CONTEXT` 11 |

评论者按原始署名字符串统计，未消歧或合并异写；标签差异不能直接归因于个人风格，因为评论者的篇目、作品、数量不同。

## 方法组合

| 两种标签 | 同时出现的篇数 | 占全部篇目 | 相对独立基线倍数 |
| --- | ---: | ---: | ---: |
| `STRUCTURE` + `TEXT_WORD` | 770 | 51.2% | 0.99 |
| `INTERTEXT` + `STRUCTURE` | 707 | 47.0% | 1.00 |
| `INTERTEXT` + `TEXT_WORD` | 575 | 38.2% | 0.96 |
| `CONTEXT` + `STRUCTURE` | 556 | 36.9% | 1.03 |
| `DEBATE` + `STRUCTURE` | 475 | 31.6% | 0.99 |
| `IMAGE` + `STRUCTURE` | 437 | 29.0% | 1.02 |
| `ALLUSION` + `STRUCTURE` | 428 | 28.4% | 1.04 |
| `CONTEXT` + `TEXT_WORD` | 423 | 28.1% | 0.92 |
| `AESTHETICS` + `STRUCTURE` | 393 | 26.1% | 0.94 |
| `CONTEXT` + `INTERTEXT` | 389 | 25.8% | 0.94 |
| `DEBATE` + `TEXT_WORD` | 374 | 24.9% | 0.92 |
| `AESTHETICS` + `TEXT_WORD` | 373 | 24.8% | 1.05 |
| `DEBATE` + `INTERTEXT` | 353 | 23.5% | 0.96 |
| `AESTHETICS` + `INTERTEXT` | 340 | 22.6% | 1.06 |
| `IMAGE` + `TEXT_WORD` | 335 | 22.3% | 0.92 |

组合按篇统计，同篇中两种标签各出现至少一次即记一次。「相对独立基线倍数」= 实际共同出现篇数 ÷（两标签各自出现篇数之积 / 总篇数）；约为 1 时，共现主要由各自的高频率解释，不能当作特殊关联。

## 使用边界

- 这是现有 AI 初标及六篇复查后的**描述性统计**，没有测量全库分类准确率。
- 数量不能表示方法的文学价值，也不能证明某评论者拥有独特方法。
- 下一步应据此挑选有代表性的原始赏析，核对分析过程，再尝试提炼可迁移的方法。
- 统计仅输出方法代码、篇数及评论者署名；不输出书籍正文、现代赏析或研究卡原文。
