# Retrieval Benchmark v0.1 Ground Truth

这份文档只记录 `evals/retrieval_cases.json` 的人工核验依据。

两个问题必须分开：

1. **关系证据**：为什么认为后来的句子与某个前代文本存在可测试的承继 / 化用关系；
2. **Corpus coverage**：实验时使用的具体 Corpus 中是否真的包含 expected target。

Corpus 中“恰好有相似句”本身不证明来源关系；反过来，关系成立但 Corpus 缺失时，也不能把 Retriever 的失败算成模型失败。

第一版只收公共材料可复核的关系，不使用私人出版社注释作为公开 Ground Truth。

## Case 1｜near_quote_yan_weng

- Query：晏几道《临江仙》“落花人独立，微雨燕双飞”
- Expected：翁宏《春残》同句
- 类型：`near_quote`
- 关系依据：
  - 古文岛《临江仙·梦后楼台高锁》赏析明确说明晏几道借用翁宏《春残》末两句：
    https://www.gushiwen.cn/GuShiWen_ec40f5ffaf.aspx
  - 品诗文“落花人独立”典故条目同样将翁宏《春残》列为出典：
    https://www.pinshiwen.com/cidian/wxdg/2019052461934.html
- chinese-poetry 可见 target：
  - `御定全唐詩/json/762.json`

## Case 2｜adapted_sushi_libai_moon

- Query：苏轼《水调歌头》“明月几时有，把酒问青天”
- Expected：李白《把酒问月》“青天有月来几时，我今停杯一问之”
- 类型：`adapted_quote`
- 关系依据：
  - 人民政协网《水调歌头》注释明确称此处化用李白《把酒问月》：
    https://mobile.rmzxw.com.cn/tranm/index/url/m.rmzxw.com.cn/c/2022-06-21/3142978.shtml
- chinese-poetry 可见 target：
  - `御定全唐詩/json/179.json`

## Case 3｜compressed_hezhou_lishangyin_jinse

- Query：贺铸《青玉案》“锦瑟华年谁与度”
- Expected：李商隐《锦瑟》“锦瑟无端五十弦，一弦一柱思华年”
- 类型：`compressed_cue`
- 关系依据：
  - 古文岛《锦瑟》赏析在解释“一弦一柱思华年”时直接举贺铸“锦瑟华年谁与度”为后世用例：
    https://www.gushiwen.cn/mingju_1599.aspx
  - “锦瑟华年”典故条目也以李商隐《锦瑟》为语本，并列贺铸词句：
    https://www.cidianwang.com/lishi/diangu/0/15110re.htm
- chinese-poetry 可见 target：
  - `御定全唐詩/json/539.json`

## Case 4｜transformed_liqingzhao_fanzhongyan_brow_heart

- Query：李清照《一剪梅》“此情无计可消除，才下眉头，却上心头”
- Expected：范仲淹《御街行》“都来此事，眉间心上，无计相回避”
- 类型：`transformed_use`
- 关系依据：
  - 古文岛《一剪梅》赏析引王士禛《花草蒙拾》，指出结拍三句从范仲淹“都来此事，眉间心上，无计相回避”脱胎而来：
    https://www.gushiwen.cn/mingju_916.aspx
  - 品诗文范仲淹词句条目也明确说李清照“才下眉头，却上心头”由此变化而来：
    https://www.pinshiwen.com/zhiyan/gscmj/2019061192294.html
- chinese-poetry 可见 target：
  - `宋词/宋词三百首.json`

## Case 5｜adapted_jiangkui_dumu_springwind

- Query：姜夔《扬州慢》“过春风十里，尽荠麦青青”
- Expected：杜牧《赠别》“春风十里扬州路”
- 类型：`adapted_quote`
- 关系依据：
  - Chinese Text Project 收录的《姜夔词选》注释明确说明“春风十里”出杜牧《赠别》：
    https://ctext.org/wiki.pl?chapter=109654&if=en&remap=gb
  - 经典古诗文网《扬州慢》注释亦列出杜牧原句：
    https://www.cn3e.cn/shiwen/songdai/200873oyb.html
- chinese-poetry 可见 target：
  - `全唐诗/唐诗三百首.json` 及其他唐诗子语料

## Case 6｜compressed_jiangkui_dumu_qinglou

- Query：姜夔《扬州慢》“青楼梦好，难赋深情”
- Expected：杜牧《遣怀》“十年一觉扬州梦”
- 类型：`compressed_cue`
- 关系依据：
  - 诗文岛《扬州慢》赏析明确将“青楼梦好”对应到杜牧《遣怀》“十年一觉扬州梦，赢得青楼薄幸名”：
    https://www.shiwendao.com/a/1043972.html
  - 品诗文《扬州慢》注释同样列出《遣怀》原句：
    https://www.pinshiwen.com/shiji/jiangkui/20210316311905.html
- chinese-poetry 可见 target：
  - `御定全唐詩/json/524.json`、`全唐诗/唐诗三百首.json`

## 关于繁简和异文

第一版 Dataset 的 Query 保留 Poeticus 当前常见的简体文本；expected target 则尽量使用 chinese-poetry 中可见的原始写法。

这意味着第一轮可能同时观察到“文本关系距离”和“繁简 / 异体差异”的影响。这里不提前做繁简统一。若 coverage validator 发现目标在所选 Corpus 中因版本差异无法匹配，先把它记为 **Corpus / normalization 问题**，而不是 Retriever miss。
