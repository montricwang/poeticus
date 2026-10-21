# 词话网站的原文版本与实质异文：2026-10 研究记录

> 取自 [#237 压缩前完整研究正文](../archive/issue-bodies-2026-10-21/237.md)，本文件是**历史实验案例**，不是校定底本或当前内容来源授权书。网址与转录为当时的网页观察；今天的服务质量、许可和内容可能变化。当前外部资源分类见[数字人文资源地图](../digital-humanities-resources.md)。

## Case A：张炎《词源》「虚字」

2026-10-12 比较公开网页时，出现**并非标点差异**的读法分歧：

| 来源 | 当时网页呈现的关键短句 | 证据范围 |
| --- | --- | --- |
| [识典《词源》](https://www.shidianguji.com/book/CYYT078/chapter/1kxs2q4zq3twl) | 「若能尽用虚字，句语自活」 | 网站整理/转录，不等于已核影印 |
| [CTP《词源》相关章](https://ctext.org/wiki.pl?chapter=62530&if=en&remap=gb) | 「若使尽用虚字，句语又俗」 | 网页正文可能受底本、OCR 或校对状态影响 |
| [施蛰存《词学名词释义》转引](https://www.aisixiang.com/data/98041.html) | 「若能善用虚字，句语自活」 | 后出研究中的引文，不能替代底本 |
| [赵惠俊研究转引](https://www.aisixiang.com/data/170407.html) | 「若使尽用虚字，句语又俗」 | 研究转引，为版本核实提供线索 |

「能/使」「自活/又俗」改变句意，必须先确定**底本、卷章/页、版本谱系、网页校订/OCR 状态**，才谈得上择定引文。平台知名度或多个网页出现同一写法，并不能独立证明其为原刻。

原研究还找到 CTP《词源》不同书目入口 [`ctp:wb762761`](https://ctext.org/wiki.pl?if=gb&res=762761) 与 [`ctp:wb860722`](https://ctext.org/wiki.pl?if=gb&res=860722)（当时页面标作《粤雅堂丛书》本）。**两入口不得无证据合并为同一个无版本全文**。

## Case B：《人间词话》汇编与 1926 朴社本

中文维基文库公开入口至少包括[《人間詞話》汇本](https://zh.wikisource.org/zh-hans/人間詞話)和[1926 年朴社本](https://zh.wikisource.org/zh/人間詞話_(1926))。研究目标不是只确认「词以境界为最上」能搜索到，而是分清篇则序列、版本描述、页面 revision ID、是否混合了未刊稿/补遗，以及引用能否返回准确正文位置。

**当时未验**：两版本的逐则全文校勘、正式 API 请求许可和允许批量公开再分发的条件。

## Case C：沈义父《乐府指迷》书目与 OCR

[CTP 沈义父本 `ctp:wb996630`](https://ctext.org/wiki.pl?if=gb&res=996630)和[另一个章节页](https://ctext.org/wiki.pl?chapter=805799&if=en)需要核对是否同一版次/文本。旧调查注意到个别网络材料存在**把《词源》相关段落误归《乐府指迷》**的风险，并观察到部分 CTP Wiki 录入标为 OCR 未校。

下一次最小核验应按一段文字保存：**作者、书名、底本/版本、卷则、原文锚点、确切引文、影印对应、校对状态、访问/许可条件**。未解决的异文保留多方来源，不改写核心 Corpus，不为了 API 能读就批量采集。

与现有任务关系：[来源研究 #237](https://github.com/montricwang/poeticus/issues/237)、[文献阅读和引用 #133](https://github.com/montricwang/poeticus/issues/133)、[版权边界 #184](https://github.com/montricwang/poeticus/issues/184)。
