# 数字人文资源地图：Poeticus 可复用的外部成果

> 更新：2026-10-12；**研究入口，不是已接入清单或许可保证。**
>
> 当前执行验证：[Issue #184](https://github.com/montricwang/poeticus/issues/184)。
> 当前 KG 选型问题：[Issue #149](https://github.com/montricwang/poeticus/issues/149)；词话产品架构：[Issue #133](https://github.com/montricwang/poeticus/issues/133)；优先收录书目：[Issue #147](https://github.com/montricwang/poeticus/issues/147)。

## 这份地图用来解决什么

Poeticus 已有：3491 首公开阅读词作、约 85 万首作品的 Hybrid Text Retrieval、CNKGraph 典故/出处 Tool、LangGraph Agent 和基础 Eval。新问题不是“还能找到多少工具”，而是：

> **前人整理好的数据、开放接口与工程方法，究竟能替我们省掉哪段工作？**

定位原则：**资源信息留在本页；是否实际验证、结果如何由 #184 跟踪；实现进对应 Feature Issue；架构决定才写 ADR。**

### 状态与“可用”的区别

- **来源页已查**：看到官方网站、代码库或正式论文；不等于我们试过 API 或读取过完整数据。
- **现成数据 / API**：存在可下载文件或接口；不代表完成字段映射、版权复核、性能测试或接入。
- **方法 / 标准**：可以借鉴原理与实现，但不是可直接使用的文献内容。
- **待核实线索**：尚无可验证的当前下载/接口/完整原文，不能规划为生产依赖。

## A. 可以直接取得材料或接入服务

| 资源与原始入口 | 已知能提供什么 | 对 Poeticus 的价值 | 状态 / 关键约束 |
| --- | --- | --- | --- |
| [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry) | 开放仓库中的诗词 JSON | 扩充/对照作品文本 | 数据来源已知；新来源进入阅读库前按 [#36](https://github.com/montricwang/poeticus/issues/36) 校勘、查重、核许可，不自动覆盖正文 |
| [Song Ci Corpus（Zenodo）](https://zenodo.org/records/17798065) | 可下载 SQLite 文件（页面列 ci_curated.db） | 用于作品和字段的对照；不包含现成词学批评网络 | **已确认下载入口，未读取文件**；记录页的 License 字段未能明确读出具体条款，复用前核实 |
| [萌典：开放 JSON API](https://www.moedict.tw/about.html) | 台湾教育部《重编国语辞典修订本》的字词、读音、义项和原文书证 | Poeticus 本地研究新工具 `lookup_moedict`；首轮实测「將息」命中，偶有网络超时 | **API 协议 CC0，辞典正文 CC BY-ND 3.0 TW**；保留字形和来源，不将候选义项等同宋词语境解释；默认关闭、尚未合并到生产 |
| [汉典](https://www.zdic.net/) / [网站条款](https://zdic.net/terms/) | 古汉语单字/词义、康熙与广韵等书证、异体及读音信息 | 经 DeepSeek `web_search(source=zdic)` 定站搜索获取词条链接；旧 #234 曾人工抓取若干字词，新 Agent 实测「䰒」搜到汉典 | 站点自称 CC0，但涉及第三方字书内容；**未见可复用官方 JSON API**，本轮不逆向抓取全站，不把单字义项机械拼成双字义 |
| [维基文库词话专题](https://zh.wikisource.org/wiki/Portal:詞話) / [《人間詞話》](https://zh.wikisource.org/zh-hans/人間詞話) | 词话数字文本、不同版本、Wiki revision / 固定链接、EPUB 导出 | [#133](https://github.com/montricwang/poeticus/issues/133) 小规模词话 Corpus 的起点；《人間詞話》汇本与 [1926 朴社本](https://zh.wikisource.org/zh/人間詞話_(1926)) 可先做版本对照 | **2026-10-20 已实现官方 Action API 搜索与按 pageid 读取修订链接**；个别真实请求网络超时，尚未完成稳定性验收；仍需逐部检查版本、卷则、缺页、错字与具体授权 |
| [识典古籍](https://www.shidianguji.com/) / [北京大学数字人文研究中心项目说明](https://pkudh.org/project/shidianguji/) | 北大与字节跳动联合研发的古籍阅读、图文对照、版本/卷章元数据、全文检索与机器粗校/人工精校体系 | **可能减少**词话原文、书目元数据、古籍 OCR/初校和全文查询的自建工作；先验证按需引用与版本定位 | **2026-10-12 用户 WSL 实测**：Tavily Extract/Firecrawl Keyless Scrape 均从《词源》卷下读到“清空”“骚雅”等候选原文，但有段落粘连；尚未找到已确认可用于第三方产品的公开 API/批量导出许可。网页免费阅读 **不等于**允许自动镜像或再分发；仅将 URL 作为候选来源 |
| [古汉语典故资源库](https://github.com/KaijieMo-kj/Ancient-Chinese-Allusion-Resource-Database) | 约 2.3 万典形、3 万余条用典标注，公开典故 JSON 和测试集 | **潜在补充 Provider / 离线评测集 / 局部替代**，不预设全量取代 CNKGraph | **2026 年 4 月末用户已调查，主观体验不佳**（具体失败记录待追溯）；README 声明数据 MIT。先复盘旧结论，只有能补真实缺口再重新实测，勿当新发现 |
| [CNKGraph 开放资源](https://cnkgraph.com/Home/OpenResources) / [Web API](https://open.cnkgraph.com/swagger) | 古籍、诗文数据包；人物、典故、出处、关系与化用等知识图谱候选能力 | **Poeticus 已接部分典故/出处 Tool**；人物/关系部分需与 CBDB、Wikidata、CTP Data Wiki 同问题对照，见 [#238](https://github.com/montricwang/poeticus/issues/238) | 官方明确提供研究学习用途 API、**仅限非商业**；尚未验证人物关系端点字段，不将网站整个 KG 当成已接入 |
| [CBDB API](https://cbdb.hsites.harvard.edu/cbdb-api) / [2026-08-20 授权条款](https://cbdb.hsites.harvard.edu/cbdb-data-licensing-terms) | 中国历代人物 ID、姓名与 JSON 传记/关系信息；亦有独立数据库资源 | 人物别名、身份与交游关系对齐 | **Poeticus 尚未实测人物 API**。2026-08-20 起：当前 standalone release 范围内的数据仍为 CC BY-NC-SA 4.0；超出其日期/体量范围的较新数据，另有禁止演绎、再分发及用作第三方公开查询服务等限制。不能因 API 对外可调用就直接接入公开 Poeticus；正式用途须逐项核对或获得授权 |
| [CTP API](https://ctext.org/tools/api/zhs) / [数字人文工具](https://ctext.org/digital-humanities) | 古籍全文、影印 / OCR 版别、书目 URN、受限 JSON API；另有 Data Wiki 书目实体与来源关系 | 逐章核对《词源》《乐府指迷》等，可能减少本地大规模古籍 OCR/录入，也给人物关系补有出处的数据 | **公开网页已核实**《词源》[多版本目录](https://ctext.org/wiki.pl?if=gb&res=762761) 与《乐府指迷》[沈义父本](https://ctext.org/wiki.pl?if=gb&res=996630)；Poeticus 未实测正式 API。官网限制匿名全文请求，不以 API 批量下载作为默认方案；部分 Wiki 文本为 OCR 未校 |
| [中华古籍智慧化服务平台（国家图书馆牵头）](https://guji.nlc.cn/) / [国家图书馆介绍](https://www.mct.gov.cn/whzx/zsdw/zggjtsg/202505/t20250522_960155.html) | 跨省馆藏数字古籍、图文对照、全文、知识检索、知识图谱与相关辅助工具 | **可能**给 #237（原文/版本）、#238（知识图谱）、#240（OCR）提供现成能力 | 开放网页入口已核实；[南京大学图书馆提示](https://lib.nju.edu.cn/info/1444/4110.htm) 精校与 AI 自动生成且部分未校文本混存。**未确认开放第三方 API、结构化 KG 查询、文本/影像再利用许可、具体书目覆盖** |
| [中华经典古籍库（中华书局/籍合网）](https://jingdian.ancientbooks.cn) / [浙江大学图书馆介绍](https://libdb.zju.edu.cn/s/lib/libtb/show/1869) | 正式整理本及注释、校勘、影像对照和页码引用 | 适合对照关键异文、人工核查权威整理本 | 多由图书馆订阅或按机构 IP/VPN 访问，**不能假定是免费开放 API 或可复制数据**；暂不作为生产主依赖 |
| [中华文库（独立网站）](https://www.zhonghuashu.com/wiki/首頁) | 网站自称收集互联网已有典籍，页面形态近 Wiki，包含古籍文本 | 补查冷门页面线索，可用于定位再回溯来源 | **与官方维基文库、国家图书馆及中华书局的中华经典古籍库均非同一机构**；来源、底本、授权与文本质量未核，暂不列权威底本 |
| [唐宋文学编年地图](https://poem.cnkgraph.com/) | 作家生平、活动轨迹、时空信息 | 辅助编年、人物/地理问题 | 已有公开平台；具体 API / 结构化导出与授权待确认 |

**注意**：技术能调用 ≠ 资料可合法复制 ≠ 资料可公开提供服务。文本的原始版本、编辑者整理成果、API 与数据库许可要分别核查；尤其不能因“古人作品属于公有领域”就默认所有现代整理版都可任意使用。

**#237 已发现可能改变词论理解的跨站异文**：同为张炎《词源》卷下「虚字」，[识典](https://www.shidianguji.com/book/CYYT078/chapter/1kxs2q4zq3twl) 作「若能尽用虚字，句语自活」，[CTP](https://ctext.org/wiki.pl?chapter=62530&if=en&remap=gb) 作「若使尽用虚字，句语又俗」；[施蛰存转引](https://www.aisixiang.com/data/98041.html) 又作「若能善用虚字，句语自活」。目前**未核对对应影印底本，不能断言何者正确**。这表明取回网页正文不能直接替代版本/篇章锚点和人工校勘；具体实验与追查集中 [#237](https://github.com/montricwang/poeticus/issues/237)。

**获取与复用分开判断**：单篇在线阅读/按需查询、可复核 URL 引用、经许可的小型本地缓存、批量下载/离线导入、公开再分发，是不同的使用方式。优先评估外部 API/网页能否替代本地的**长尾候选查询**；核心作品阅读与词话连续阅读是否仍要自有 Document Corpus，按 [#133](https://github.com/montricwang/poeticus/issues/133) 的原文定位、离线可用性和版本要求决定。参见 [#184](https://github.com/montricwang/poeticus/issues/184) 与 [#235](https://github.com/montricwang/poeticus/issues/235) 的真实试验；当前**没有决定弃用 RAG / 本地 Corpus**。

## B. 主要给现成代码、评测或方法

| 项目 | 已知提供什么 | Poeticus 应当借鉴什么 | 当前判断 |
| --- | --- | --- | --- |
| [ACP-RAG（NAACL 2025）](https://github.com/SCUT-DLVCLab/ACP-RAG) / [论文](https://aclanthology.org/2025.findings-naacl.46/) | 语料、问答任务与评测的研究；公开索引、检索、排序、过滤等 Pipeline 代码 | 对照已有 Dense / BM25 / RRF 和 Eval；查漏，不整体搬运 | **代码为 MIT，但论文数据是非商业研究许可且需要机构申请**；部分评分模型尚待发布。它是可研究的菜谱，不是立刻可导入的完整数据 |
| [SCAD 用典识别（2026）](https://www.nature.com/articles/s41599-026-06627-z) | 典故知识库与用典识别方法的研究 | 用典识别、反例、难例评测 | 已找到论文；仓库与完整模型/数据的可运行性、许可证尚需单独核验 |
| [AncientTRD 古文文本复用检测（2025）](https://www.mdpi.com/2076-3417/15/19/10475) | 文本复用、改写与相关评测设计 | 对照 [#119](https://github.com/montricwang/poeticus/issues/119) 的互文发现与证据区分 | 方法参考；是否有可用数据/实现需要核实 |
| [《古诗词图谱的构建及分析研究》（刘昱彤等，2020）](https://doi.org/10.7544/issn1000-1239.2020.20190641) | 词汇—注释—语义分类图谱，实验用唐诗分类与情感任务 | 词语/意象层级的初步建模 | **已审阅用户提供的论文全文**：标签按词/标题规则自动生成，不能把分类 F1 直接当成文学理解能力；不等于词学批评史图谱 |

ACP-RAG 与 Poeticus 当前 Text Retrieval 有显著功能交集。**不因另一篇论文指标高就另造一套 Pipeline**：必须同数据、同问题、区分 Retriever 找不到与 Agent 用不好两类失败。

### EPUB 内容解析（工具，不是现成史料）

| [EbookLib（Python）](https://github.com/aerkalov/ebooklib) | 解析 EPUB2/3 的目录、spine、书目元数据与 XHTML 正文 | 先用普通 Python 阅读已有合法 EPUB，再评估与 Poeticus Document Schema 的对齐；不必因为遇到 EPUB 就先找一个 MCP Server | 读取能力有官方样例；**Poeticus 对真实词话 EPUB 的章节/注释定位尚未做本轮对照**；库本身为 AGPL，依赖选择需另核对 |

## C. 数据组织标准：不自造原文锚点与版本规则

| 标准 / 工具 | 已解决的问题 | 应用态度 |
| --- | --- | --- |
| [TEI P5](https://tei-c.org/release/doc/tei-p5-doc/en/html/) | 电子文本、卷章节、标注、校勘及版本表示 | 先学习其模型；不要求 Poeticus 全库改为 TEI XML |
| [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) | 一段评论如何指向原文的确定位置 | 特别适合参考 [#133](https://github.com/montricwang/poeticus/issues/133) 的“评论 → 作品 / 原文 / 上下文”链接语义 |

**当前缺口不是没有标准，而是尚未选定最小、可落地的评论定位契约。** 优先用 2–3 部真实词话检验，再考虑统一 Schema。

## D. 尚待核实的数字人文项目与论文线索

| 线索 | 能解决什么的可能性 | 未确认什么 |
| --- | --- | --- |
| [香港中文大学古典文学批评数据库项目（2023 报告）](https://research.cuhk.edu.hk/en/publications/teaching-challenges-and-opportunities-of-classical-chinese-litera/) | 报告称计划支持 200 多种诗话/词话全文检索、MARKUS 标注、文本分析，**若已开放，可能大幅减少 #133 的采集工作** | **截至本次调查，没有确认当前可公开访问的成品系统、API 或下载；2023 年表述为在建，不能当现成服务** |
| [OpenKG 古诗词图谱](http://data.openkg.cn/dataset/shici) | 约 28 万规模关系数据的线索（数字由其他模型提供） | 页面、可下载数据、完整 Schema、实际 dataset-specific license 尚未验证，**不可认定可按 CC-BY 商用** |
| [爱图谱 / TechKG](http://www.neukg.com/) | 现代学者与“词学批评”等研究术语的关系 | 主要是现代学术研究主题图，不应误认为「张炎—姜夔—词论」历史批评图；下载与复用仍待核实 |
| 「绝妙好词——宋词语汇网络」 | 早期宋词语汇本体 / OWL 实践 | 原始网站与数据现状未找到；作为方法史参考 |
| 《宋词知识图谱构建及应用研究》（王绪月，2025；DOI: 10.27283/d.cnki.gsxcc.2025.000378） | 可能有宋词关系 Schema 参考 | 尚未审阅全文，不预设论文质量 |
| [《融合知识图谱与大模型的宋词智能问答方法》（2026，万方题录线索）](https://d.wanfangdata.com.cn/periodical/jsjgcysj202607035) | 图谱 + Qwen2-7B + LoRA 的设计线索 | 全文、代码、数据、评测指标含义尚待独立核对 |

「存在论文 / 项目介绍」≠「存在可生产使用的工具」；不要用论文 F1、节点规模推断 Poeticus 会提升多少。

## E. 先验证谁，什么时候停止

1. **先完成现有 CNKGraph 的真实问题评测**：复盘四月已经调查过的典故库，只有发现与当前缺口相关的新增能力，才做少量补充测试；也允许只借它的标注作为 Eval，不接入生产。
2. **优先调查词话资源的可获得性**：维基文库实际文本 + 香港中文大学项目现状；这可能决定 #133 需要自行整理多少。
3. **核对现有 API 的授权与事实查询价值**：CNKGraph 已在用，CBDB / CTP 尚未接；先测 3–5 个实际问题，不默认扩大到所有接口。
4. **最后才比较新的检索框架、语义图谱**：只有现有 #119 / #133 的真实 Case 体现明确缺口，才开展方法迁移或自建。

每轮小实验只需要记：样本 / 实际取得的数据或响应 / 原始来源 / 许可 / 与当前系统的对照 / 结果 / 是否值得接入。结果记在 [#184](https://github.com/montricwang/poeticus/issues/184)，有长期价值的外部资源事实再更新本页。

## F. 不应该放在这里的内容

- **哪些词话首先收录**：[#147](https://github.com/montricwang/poeticus/issues/147)
- **词话如何阅读、建立 Document Corpus**：[#133](https://github.com/montricwang/poeticus/issues/133)
- **Text Retrieval 当前方法与实验**：[#119](https://github.com/montricwang/poeticus/issues/119)、[Text Retrieval 架构](architecture/text-retrieval.md)
- **知识图谱 Schema / 低承诺谓词 / 是否上 Neo4j**：[#149](https://github.com/montricwang/poeticus/issues/149)
- **Persona / Skills / Notebook**：[#148](https://github.com/montricwang/poeticus/issues/148)
- **自主出题与证据自校验**：[#150](https://github.com/montricwang/poeticus/issues/150)

**先复盘已做工作，再按实际缺口验证替代或互补；不因发现新项目就重新选型。**

## G. 复用不是「API 能通」：来源、权限与产品用途分开判断

为一个读者问题调查外部资源，先记录三件互相独立的事：

1. **内容层**：是否确有这部书、这位作者或这段原文？是否给出原始版本、卷次、页/条定位；普通搜索摘要只能算候选。
2. **访问与许可层**：网页能打开、第三方 MCP 能返回、官方 API 能 HTTP 200、可以缓存/公开再分发，是四种不同承诺。未经确认不能批量镜像、绕过站点规则或把非商业研究数据直接开到公网。
3. **产品层**：用户究竟要一次释义、带来源的片段，还是连续阅读全文/版本比较？按需查询可复用外部 API；需要稳定阅读与来源回跳的文献则可能要经授权本地收录。不能笼统宣布「外包给 MCP」或「一律自建 RAG」。

已有实际警示：[《词源》「虚字」段跨站对照](https://github.com/montricwang/poeticus/issues/237)出现「若能尽用」与「若使尽用」等**改变句义**的读法差异；在未对应可信影印及具体版本前，不能仅按平台声誉宣布哪条是真本，也不能把网页 OCR 当成整理底本。

一次实验只交付**样本、可复核来源、内容差异、许可/成本、比现有工具多解决了什么、采用或暂缓结论**。可用资源事实记在本页，任务验收在 [#184](https://github.com/montricwang/poeticus/issues/184)；实际接入 Agent 的代码与路由有独立任务，不在资源地图里维护第二份实施进度。
