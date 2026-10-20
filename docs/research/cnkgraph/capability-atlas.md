# CNKGraph 能力资产与复用手册

> 调查日期：2026-10-20。工作范围：官方公开 Postman + Swagger。关联 Poeticus [#346](https://github.com/montricwang/poeticus/issues/346) / [PR #353](https://github.com/montricwang/poeticus/pull/353)。
>
> **定位**：这是给未来自己和 AI 协作者查阅的长期技术资产，既是发现目录，也是复测入口。此文档不代表已经确定要接入这些功能，也不要求现在实现一个 CNKGraph UI。

## 一、先回答未来最可能遇到的问题

| 以后遇到的问题 | 直接翻阅 |
| --- | --- |
| “有没有古书原文、某段话在哪本书里、如何定位到卷？” | 第三节「古籍与类书」、附录 Book/Category |
| “这个词语是否典故、见于何书？” | 第四节「典故、字书」 |
| “某首词平仄、押韵、变格如何？” | 第五节「词谱、韵典与词律校验」 |
| “诗文中的人名、地名、典故可否用外部 ID 查询？” | 第六节「实体、人物、作品」 |
| “宋代的某年某月是哪年？某人去过哪里？” | 第七节「年历、地理、生平」 |
| “有没有更冷门的能力，比如相似句、集句、曲谱、丝路？” | 第八节「其他发现」 |
| “某个具体 API 之前到底测过没有，返回什么字段？” | 第十节全量接口目录 + HTML 报告、原始批次 JSON |
| “准备把能力给 Agent 使用，该遵守什么边界？” | 第九节「Agent 使用方式」 |

**原始资产层次**：

1. 本文：人工解释用途、证据、失败和复查路径。
2. [深色 HTML 报告](cnkgraph_audit_report.html)：156 条逐项观察，可搜索、展开、人工备注和导出 JSON；离线打开，不会发网络请求。
3. [api_inventory.json](api_inventory.json)：官方 Postman 实例与 Swagger Schema 清单。
4. probe_batch_0.json ～ probe_batch_4.json：状态、耗时、响应结构和跳过理由。这里不保存受版权限制的整篇正文。
5. [官方开放资源说明](https://cnkgraph.com/Home/OpenResources)、[Swagger](https://open.cnkgraph.com/swagger/index.html) 和 [Postman 包](https://open.cnkgraph.com/Api/postman.zip)：下次复测以官方为准。

## 二、范围与“验证成功”的含义

本次发现 **12 个 Postman 领域、71 条示例请求（64 组字面方法+路径）**；Swagger 公开 **18 个标签、103 条路径、105 个 HTTP 操作**。按照原始字符串比对，又增加 85 条 Swagger 补充记录，共留存 **156 条记录**。这不是 156 个独立的 API：不同示例参数、路径模板大小写、同一能力的多种写法会重复。

自动探测状态分布：

| 状态 | 记录数 | 含义 |
| --- | ---: | --- |
| valid_shape | 92 | 有可解析的 JSON，已登记响应字段；**未验证内容正确** |
| partial_truncated | 23 | 响应体较大，读取上限 100 KiB；不得推断完整内容 |
| http_error | 17 | 本次输入返回错误；占位 ID 或请求体可能有误 |
| unexpected_response | 5 | 204、302 或非预期类型；可能是文件、跳转或空响应 |
| network_error | 3 | 单次连接/超时失败，不是长期不可用结论 |
| not_tested | 16 | 有意不请求导出、协议及不适宜自动探测的端点 |

通用批次使用串行低频请求、每次至少间隔 0.5 秒、12 秒超时、读取最多 100 KiB，不做整库下载、登录、批量导出或写操作。

**两种证据必须分开看**：

- *批次观测*：上述 JSON，记录响应形状、状态码和测试输入；不足以证明语义。
- *2026-10-20 定向补充实测*：在后续对话里使用已知作品/书卷、合理关键词进一步核实，下面仅保留短摘要。这些结果尚未逐条添加到原始五份批次 JSON，不要误称为已完成全领域验收。

**明确的约束**：官方开放 API 限非商业研究学习。个人低频实验、生产公开服务、缓存、批量入库和再分发具有不同的许可风险。未来商业/公开接入前必须明确授权。公开可读的正文也不等于允许建立镜像。

本次资料的 SHA-256：Postman cf8ed129682f67a7df6033893ee3cbcd97109a0808dd3d72aa1f6767033a21f3；Swagger f0c0fac7baccdce5633e6e0f4f7d53ed4c67ff5f9c34aa864aa5ce3081b27a9f。将来 SHA 变化，应重新核查文档与请求契约。

## 三、古籍与类书：可以“查原文”，不只“查书名”

### 3.1 Book：书目、版本、全文检索、按卷取文

**已经得到的证据**：

- GET /api/book：书籍分类与总量。
- GET /api/book/史部/正史类：本轮返回 119 条书目数据，包括书名、作者、朝代、版本。
- GET /api/book/2180：ID 2180 是《史记》，返回 **4 组版本资源**，有影印与文本版本、按卷的 URL 等信息。版本可能来自 Kanripo、Archive.org 等，需要分别辨认来源及权利。
- POST /Api/Book/Find：以“黄鹤楼”为关键词检索，返回 Count = 5853、命中书/卷及命中前后文。结果结构含 Book、BookId、Volumes、VolumeId、PreviousText、MatchedText、LaterText。**5853 是匹配计数，不是 5853 部不同的书**。
- Postman 中“黄鹤？楼”通配符与“黄鹤楼 鹦鹉洲”多词查询都得到 JSON；具体组合语义尚未测试。
- GET /api/book/volume/KR4h0140_024：确实返回一卷《御定全唐诗》的 Text + Html。后续短量测试观察到文本约 1.15 万字符、HTML 约 3.35 万字符；仅留大小和字段，不收录整卷正文。

**关键坑：路径大小写/协议不一致。** Postman 的 POST /Api/Book/Find 可用；同轮定向试探的 Swagger 写法 POST /api/Book/Find 返回 404。Swagger 的 GET /api/Book/Volume/{id} 对占位 ID 90 返回 404，但真实卷 ID 可用；不能把占位错误当作接口废弃。POST /api/Book/Search 首轮有正常形状，后续一组请求出现 404，需按字段/请求体/路由复验。

**给 Agent 的用途**：按关键词找到“书 → 卷 → 短命中片段”，必要时取卷上下文；从自己 Document RAG 看到某个词学评论后，反查其所引古籍。优先让模型接收短引文、出处定位、版本来源及疑点，不让模型一次读取大书，也不让外部查询自动写入 Poeticus 主库。

**下次复测**：5 个已知原文与书卷的金标准；精确检索、模糊检索、分页、单书过滤、简繁切换、同文本异本差别。比较真实书卷定位准确率而非仅看 HTTP 200。

### 3.2 Category：按主题找古人汇编的文献

类书适合“知道主题，不知道原文关键词”的问题。

- GET /api/category：首轮返回 8 种类书。
- POST /api/category/find，输入“潮州”：发现《钦定古今图书集成》《骈字类编》《方舆胜览》等类书及条目 ID。
- GET /api/category/方舆胜览/0086：返回“潮州”的“建置沿革”“郡名”“古地名”等子条目，部分 SubItems 提供解释原文。
- GET /api/category/渊鉴类函/0024：返回“律”条目及分类内容；个别类书全文响应大而被截断。

**给 Agent 的用途**：讨论“黄州有哪些古地名”“宋人如何理解某个意象”时，让类书充当专题索引。但类书引用可能删节、误抄、晚出，模型不应将汇编文字直接当作原书版本。

**下次复测**：不同主题各选一条，核实子条目到原书引文的可追溯关系。

## 四、词汇、典故与字书

### 4.1 Glossary 典故 API 已经能提供原典线索

- GET /api/glossary/典故/1000：返回“不识一丁”及其他异名；字段含 Keys、CountInWritings、Quotes 等；定向查询中 Quotes 有《新唐书·张弘靖传》的书目位置。
- POST /api/glossary/典故/find，搜索“桃花”：得到桃花源/武陵源、桃花水、人面桃花等候选。各自有本站的作品使用统计，但统计不是全部文学史的客观总数。
- 词典与佛典端点返回词条、原字形、解释、来源/分类等；另有批量查询与分类词表。

### 4.2 Char：独立单字训诂

合法单字 GET /api/char/中，已有现代字典、《康熙字典》、《说文》类字段的有效响应。Swagger 补测另一次使用不适配的占位参数报错，所以保留两种结果，不简单判断全类失效。

**给 Agent 的用途**：回答词义、典故来源、异体字、古今义差别，或复核来源而非靠模型凭记忆解释。Poeticus 现有 lookup_allusion 应当先对比效果，不要新建功能等价的重复 Tool。

**下次复测**：不同用法的“桃花”“青鸟”“章台”与非典故普通词；来源是否可追、误认率多少。

## 五、词谱、韵典、曲谱与格律分析

这里在后续对话进行了更具体的正反试验。

| 能力 | 实测证据 | 给 AI 的价值 | 未解决的边界 |
| --- | --- | --- | --- |
| CiTune 词牌 | ID 90 是《醉花间》，返回 3 种格式、字数韵位、例词；ID 614《念奴娇》有别名与不同体式 | 在分析作品前查真实词谱、变格与例词 | 后世词谱与宋代实际演唱不可混同 |
| CiTune/Pattern | “对潇潇暮雨洒江天”查询得到候选 | 依据句式/格律寻找可能的词牌 | 候选不一定唯一 |
| Rhyme 韵典 | 返回平水韵、词林正韵、中原音韵、中华通韵；平水韵 106 类 | 按韵书查字的韵部与同韵 | 多音字、入声、诗韵与词韵要区分 |
| Tool/AnalyzeCi | 《醉花间》完整例词得到钦谱/龙谱结构；改末句“夕”为“春”，两套结果均指出错韵 | 由工具核对韵脚，再让模型解释 | 仅完成一组正反样本，未完成变格、多音、异文评测 |
| Writing/{id}/Tones | 苏轼作品 ID 136925 返回逐句逐字 Character/Tone | 给模型结构化声调依据 | 需核作品匹配与不确定读音 |
| QuTune 曲谱 | 目录、曲牌、格式、例作有可解析响应 | 未来扩至曲牌文学或比较词曲 | 当前并非主线，不代表有宋代曲调录音 |
| Tool/AnalyzePoem | 一次超时，无有效业务结果 | 将来分析律诗 | 需单独复测 |
| Tool/AnalyzeCouplet | 返回结构化分析 | 可研究对仗/对联 | 尚无质量验收 |

**禁止偷换概念**：“平仄/押韵符合词谱”不等于“符合宋代演唱的音乐”。例如李清照在《词论》中批评苏轼等人不协音律，Agent 可以用词谱核查作为引子，但还应检索她的原文与宋词音乐史材料，不能把某个押韵检测视作文学史结论。

## 六、人物、作品、实体标注与知识图谱

这部分最适合辅助 AI 建立查询关联，**Poeticus 仍然使用自有作品正文和内部 ID**。

- People/Find：查“苏轼”，返回人物 ID 29937、朝代及生卒字段。传统纪年与公历转换口径要另核。
- Tool/LabelAndResolveEntity：输入“苏轼在黄州写下《念奴娇·赤壁怀古》”，返回苏轼 People:29937、黄州 Region:CN421102 及属性；黄州关联到当代黄冈市黄州区。**“念奴娇”“赤壁怀古”本次被标为 Vocabulary 而非词牌/作品**。
- 另输入“大江东去，浪淘尽”，才返回 CiTune:614，可查到《念奴娇》词牌及别名。说明自动标注需要领域上下文消歧。
- Writing/136925：苏轼《沁园春》含作者、朝代、正文句段及 11 条知识链接等；Writing/{id}/Labeling 可得到作品预标注。**自动标签可能把版本说明或单个词当人物**。
- Writing/{id}/BookLinks：可返回关联古书、卷页与匹配位置。一次命中《后山诗注》卷四中的“沁园春”字样；**匹配存在不代表它就是该词的原始版本来源**。
- People/{id}/Mentionship：人与人之间的“述及/被述及”关系；这轮部分为 CSV 或占位 404，尚未验收。Poem 则另外提供作品、地图、引用、近似句、同韵等信息。

**给 Agent 的用途**：从用户问题识别外部实体 → 查结构化背景 → 用自己的文献/诗文知识库核对 → 生成解释和可回查证据。外部 ID 应放在候选匹配层，例如记录 (内部作品 ID, 提供方, 外部 ID, 匹配依据, 验证时间)，绝不直接覆盖主键或静默改正作品正文。

**下次复测**：同名不同人、一个词牌多个别名、同题不同作品、异体字、错误识别四种反例；优先看误链接率。

## 七、年历、地理、生平及专题信息

### Calendar 历法

可查朝代、年号、干支、古人具体日期及关联实体。GET /api/calendar/date/宋绍兴五年七月丁酉，返回年份 1135、乙卯、七月二十六、丁酉及年号/朔闰信息。适合 AI 理解年谱与古文中的时间，不能只凭一个干支推算唯一年份。闰月、改元与精确公历日期还需专项验证。

### Map 历史地理

返回行政区域层级、地名别称、景点、经纬度与知识链接。查杭州西湖得到“西子湖”“钱唐湖”等异名与坐标。人物苏轼的 MapInfo 返回眉山等带坐标的地点。地理关系可帮助 Agent 解释人物活动和作品地理，但**现代行政区映射不是历史边界**。链接/官员分布类端点结果常过大或属于 CSV，不宜凭首轮截断结果当完整可用。

### Biography 人物生平/行迹

Swagger 能按作者、交游对象、起止年、地点检索行迹与作品统计；还提供地点、作品事件关联和导出。定向查询苏轼某年行迹返回含 Traces 和坐标的较大 JSON，体积超过 500 KB，**尚未核实其中具体事件和原始史料锚点**。长期可供 Agent 回答“某人在某年在哪里”，但先要建立来源可信度。

### SilkRoad 丝路专题

有行旅/线路与注释节点接口；首轮响应大而截断。暂未确认与 Poeticus 的直接使用场景，**保留能力，不提前删除**。

## 八、其他长尾能力：不知道以后会怎么用，也要留下

| 现有接口/能力 | 未来 Agent 可能要解决的事 | 当前状态 |
| --- | --- | --- |
| Tool/Reference | 句子出处、化用、引用线索 | 仅返回结构已通过，误报/化用类型需查 |
| Writing/SimilarClauses、Poem/SimilarClauses | 找相似句与潜在承袭关系 | 部分 Writing 路径返回 302；Poem 有成功形状 |
| Writing/SameRhymes、Poem/SameRhymes | 找用相同韵组的作品 | 首轮响应成功，具体“同韵”算法未知 |
| Writing/SameClausePattern | 找同句式、同对仗结构 | 首轮超时，待重测 |
| Writing/CreatedGlossary | 找某词可能的首用或新创 | 只见字段成功，不能直接断言历史“首创” |
| Writing/UsedByCento/Author | 后世哪些集句复用了作者作品 | 大响应截断 |
| Writing/BookLinks、Poem/BookLinks | 文字出现在哪些书卷与注本 | 有结构化匹配；关系类型未验 |
| Tool/CharsetConvert | 简繁归一化、跨版本检索 | Postman 示例有效；不能改写原文存储 |
| Tool/Texting | 文本快速解析/HTML | 首轮可解析，实际业务与安全未核 |
| Label + 标签查询与导出 | 找知识图谱中同标签作品 | 部分接口未测或占位失败 |
| QuTune | 曲牌格式与例作 | 形状成功，待后续需要时复测 |
| Mcp /mcp、/api/mcp | 官网可能存在 MCP 协议端点 | **有意未测**；不能猜测协议/权限 |
| WeChat | 微信消息或服务器校验 | 非文学知识工具，未测 |
| 大批量 CSV/Excel/Text Export | 导出数据集 | 为保护服务与许可未请求，不应将其视为可合法镜像许可 |

旧 POST /api/tool/labelize 仍为 404；新 POST /api/Tool/Label、POST /api/Tool/LabelAndResolveEntity 是**不同的接口**，本轮返回标注和实体详情。旧清商项目 2026-06-20 对 labelize 的 31 次请求均失败，不要混成“旧 API 已修复”。

## 九、后续给 Agent 使用的建议（候选，不代表要立即实现）

我们的目标仍是 **ReAct Agent 自主决定是否检索、调用哪个工具以及是否继续核查**。尽量减少人工设计固定“先 A 后 B 再 C”的流程。

下表只是供选用的**能力语言**；它们不必与底层 API 一一对应，也不必一次全部放进 Prompt：

| 能力组 | 候选 Tool 名称 | 最小职责 |
| --- | --- | --- |
| 古籍 | search_classical_books / read_book_volume / lookup_book | 查书、命中片段、必要时补卷上下文 |
| 类书 | search_classical_categories / read_category_item | 从主题检索古人已有资料汇编 |
| 典故字书 | lookup_allusion / lookup_classical_word | 追溯词语、典故与解释（先复用现有 Poeticus 工具） |
| 词律 | lookup_ci_tune / lookup_rhyme / analyze_ci_meter | 查规则、验格律，交由模型解释 |
| 实体与诗文 | resolve_entities / lookup_external_annotations / search_external_writings | 发现和复核人物、词牌、作品的外部链接 |
| 历法与史地 | resolve_historical_date / lookup_historical_region / explore_biography | 时间换算、地点与人物行迹 |
| 相似句 | search_similar_clauses / lookup_reference | 追溯相似表达与化用线索 |

十几个 Tool 并不必然过多；**真正需要验证的是模型能否选对、用对、及时停止**。如果模型反复调用错误接口、误解工具语义或浪费大量上下文，再据 Trace 调整 Tool 描述、拆分/合并工具或预算；不要在没有失败证据时提前造复杂编排。

最低限度仍需五条工程边界：

1. **真实、可区分的结果契约**：成功有数据、成功零命中、接口超时、权限受限、占位参数错误不能全都变成空列表。
2. **证据可回查**：把来源书/卷、韵书/词谱版本、实体 ID、匹配字段等交给 Agent；必要时二次核对。
3. **本地数据库权威性**：Poeticus 正文与 ID 由自己的主库决定；外部注释/关系不自动写回。
4. **延迟与失败限制**：给工具超时、响应摘要上限与调用预算。先做真实对话的薄片测试，不预设复杂 Planner。
5. **许可约束**：非商业研究可进一步探索；公开/商业调用、缓存、批量导出、全文再发布均须核权。

一个值得测的自然问题是：“李清照批评苏轼不协音律，能拿一首词验证她批评的是什么吗？”观察 ReAct Agent 是否自主组合 **文献 RAG + 词谱/格律分析 + 必要的古籍原文核对**，而不是人为写死这个链路。

## 十、下次怎么找回来、怎么复测

- **触发**：未来遇到没想到的文学史问题、现有典故工具漏查、Agent 经常错答、外部文档更新、获得新许可。
- **找接口**：先读此文的能力说明；再用下方完整接口索引查 method/path/编号；到 HTML 报告按编号（P01～P71 为 Postman，S01～S85 为 Swagger 补测）查看输入和响应字段。
- **先做单次低频验证**：选真实且明确的已知 ID/词牌/书卷，做一个合理输入和一个反例。记录目标字段、实际业务结果、来源、时间与失败情形；不要整库遍历。
- **再判断是否接入**：观察 Agent 调用是否提升真实回答，能否正确解释并引用；若不能，修描述、参数/契约，或保留在资产库，不必继续扩大。
- **更新本档案**：业务结论变更时，补充日期和样本；原始 JSON 是历史快照，不能无提示覆盖。原始探测入口见 README 的复现命令。
- **记录未完成的问题**：Book 路由大小写/请求体、词律变格/多音、实体类型误判、古籍引用关系、年历转换、人物行迹史料、非 JSON/CSV/重定向与超时，以及版权/生产授权。

## 十一、全量接口索引（自动生成）

这部分保留官方 Swagger 105 个 HTTP 操作、Postman 71 条示例的逐项状态/字段。补充探测的路径可能与已有 Postman 实际路径语义重复。**状态仅代表这一次输入。**

<!-- BEGIN GENERATED API MATRIX -->

### A. Swagger 完整 HTTP 操作目录（105 项）

18 个 Swagger 标签。‘参见 P’表示该操作在清单构建时被视作已有 Postman 覆盖；这**不是**语义或业务验收。其他项给出 Swagger 补测时的状态。相关参数 Schema 详见 api_inventory.json / HTML 报告。

#### Swagger / Biography

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Biography` | 查询诗人生平（事件时间线、交游、活动轨迹等）。 | `partial_truncated` (200) · S01 | unparsed; TravelTraceData |
| `GET /api/Biography/WritingStat` | 按时间/作品统计诗人创作概况（例如分年度字数、篇数等）。 | `partial_truncated` (200) · S02 | unparsed; WritingStatResponse |
| `GET /api/Biography/Places` | 获取所有（或指定时代分界）活动地名称及其对应的活动条目键集合。 | `partial_truncated` (200) · S03 | unparsed |
| `GET /api/Biography/Places/{id}` | 根据模糊或层级地址解析当前（“当代”视角）对应的活动地点列表。 | `valid_shape` (200) · S04 | Category、Places; ModernPlacesResponse |
| `GET /api/Biography/Poems/{key}` | 按作品 key 查询其关联的活动 / 生平事件信息。 | `unexpected_response` (204) · S05 | non_json; TravelTraceData |
| `GET /api/Biography/Stat` | 按年份范围统计传记数据（例如活动或作者相关度量）。 | `valid_shape` (200) · S06 | AuthorCount、BeginYear、EndYear、PoemCounts、ArticleCounts、FuCounts、CiCounts、ByRegion; ArticleStat |
| `GET /api/Biography/Export/{key}` | 以 CSV 格式导出指定作家的行迹数据。 | `not_tested` · S07 | — |

#### Swagger / Book

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Book` | 获取全部典籍分类与分组概要统计。 | 参见 P 实例 | —; BookCategoriesSummaryResponse |
| `GET /api/Book/{category}/{group}` | 按主目録 + 次目録列出书籍。 | `valid_shape` (200) · S08 | Category、Group、Books; BooksInGroupResponse |
| `GET /api/Book/{id}` | 按书籍 ID 获取书籍详细（含版本与卷）。 | `valid_shape` (200) · S09 | Book; BookDetailResponse |
| `GET /api/Book/Volume/{id}` | 获取某卷全文与 HTML。 | `http_error` (404) · S10 | Message; VolumeContentResponse |
| `POST /api/Book/Find` | 复合检索：关键词 + 多书（Find）。 | 参见 P 实例 | —; KanripoSearchResult |
| `POST /api/Book/Search` | 简单检索：关键词 + 可选单书（Search）。 | `valid_shape` (200) · S11 | Count、PageSize、Key、PageNo、Notification、Summary、Result、Error; KanripoSearchResult |

#### Swagger / Calendar

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Calendar` | 获取所有（排除“近代”段）朝代及其子朝代（若存在多政权）的起止年份信息。 | 参见 P 实例 | —; CalendarDynastyListResponse |
| `GET /api/Calendar/{dynasty}` | 根据朝代或子朝代名称获取其下所有细分政权（子朝代）及君主年号信息。 | `valid_shape` (200) · S12 | Name、Dynasties; DynastyDetailResponse |
| `GET /api/Calendar/EraYear/{key}` | 根据年号键（年号 ID 或日期文本）解析并返回君主及相关年号集合。 | `http_error` (404) · S13 | str; KingEraYearsDto |
| `GET /api/Calendar/GanZhi/{key}` | 解析干支（如“甲子”）列出所有可能公元年份及该年对应的年号分组。 | `http_error` (400) · S14 | str; GanZhiResponse |
| `GET /api/Calendar/Date/{key}` | 解析日期（可含年号、闰月、干支等），返回结构化日期、年号候选分组、相关链接统计与朔闰表。 | `valid_shape` (200) · S15 | Date、EraYears、Links、ShuoLeapTable; DateParseResponse |
| `GET /api/Calendar/Date/{key}/Links` | 获取日期（唯一年号）在知识图谱中的关联实体分页结果。 | `valid_shape` (200) · S16 | Date、Links; DateLinksResponse |

#### Swagger / Category

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Category` | 獲取所有已加載的類書（類目典籍）名稱清單。 | 参见 P 实例 | —; CategoryBookListResponse |
| `GET /api/Category/{book}` | 按類書名稱獲取其所有分類與條目概要（僅返回精簡字段，不含正文內容）。 | `partial_truncated` (200) · S17 | unparsed; CategoryBookDetailResponse |
| `GET /api/Category/{book}/{itemId}/{volumeId}` | 取得某類書中指定條目（以及可選卷內容）詳情。 | `partial_truncated` (200) · S18 | unparsed; CategoryItemSummaryDto |
| `POST /api/Category/Find` | 按關鍵字全文檢索所有類書，按書籍分組返回匹配條目概要。 | 参见 P 实例 | — |

#### Swagger / Char

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Char/{key}` | 查詢單個漢字的多來源字典與訓詁信息。 包含：現代字典（自建/綜合）、《康熙字典》、《說文解字》。若某來源無資料則為 null。 | `http_error` (404) · S19 | Message; CharDictionaryResponse |

#### Swagger / CiTune

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/CiTune` | 獲取全部詞牌（不含具體格式列表），返回基礎資訊集合。 | 参见 P 实例 | — |
| `POST /api/CiTune/Find` | 按關鍵詞搜索詞牌（名稱或別名 / 規範化後模糊匹配）。 | 参见 P 实例 | — |
| `POST /api/CiTune/Pattern` | 透過輸入的詞譜模式（格律 / 平仄與字數模式）匹配可能的詞牌格式。 | 参见 P 实例 | —; CiTunePatternResponse |
| `GET /api/CiTune/{tuneId}/Writings` | 獲取指定詞牌的例詞（按朝代分類）與基礎信息。 | `valid_shape` (200) · S20 | Id、Name、Writings; CiTuneWritingsResponse |
| `GET /api/CiTune/{tuneId}/Writings/Export` | 獲取指定詞牌的例詞 Excel 文件。 | `not_tested` · S21 | — |
| `GET /api/CiTune/{tuneId}/Writings/Export/Text` | 獲取指定詞牌的例詞純文本文件。 | `not_tested` · S22 | — |
| `GET /api/CiTune/{tuneId}/{formatIndex}` | 獲取詞牌詳情；可指定格式索引返回單一格式並支援高亮匹配片段。 | `valid_shape` (200) · S23 | Id、Name、Format; CiTuneSingleFormatResponse |

#### Swagger / Glossary

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Glossary/{category}/{id}` | 按类别与唯一 Id 获取单个词条或典故。 | `valid_shape` (200) · S24 | CountInWritings、Keys、RelatedPersons、Correlations、References、Quotes、Explains、Kind、Id; GlossaryAllusionDto |
| `POST /api/Glossary/{category}` | 按类别批量获取多个词条或典故。 | `valid_shape` (200) · S25 | array |
| `POST /api/Glossary/{category}/Find` | 按类别与关键词检索典故或词汇。 若检索到典故集合则返回典故；否则返回首组匹配的词汇。 | `valid_shape` (200) · S26 | array |
| `GET /api/Glossary/CategoryWords/{category}` | 按“分类”获取对应词汇列表（含 Id）。 | `valid_shape` (200) · S27 | Category、Words; GlossaryCategoryWordsDto |
| `GET /api/Glossary/CoupletTrain/{id}` | 获取对语链 | `http_error` (404) · S28 | Message; CoupletWordTrain |

#### Swagger / Label

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Label/{type}/{id}/{subId}` | 获取指定标签（支持带子标识）对应的标签数据与分页内容。 | `http_error` (400) · S29 | errors、type、title、status、traceId; LabelDataResponse |
| `GET /api/Label/Writing/Export/{Category}` | 按标签及可选分类查询知识图谱中的作品，并导出为 CSV 文件。 | `not_tested` · S30 | — |

#### Swagger / Map

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Map/Region` | 获取最高层级国家 / 区域树（含子级概要与关联链接数量）。 | 参见 P 实例 | — |
| `GET /api/Map/Region/{key}` | 按关键字（名称模糊）搜索区域，返回匹配区域集合。 | `http_error` (404) · S31 | Message |
| `GET /api/Map/Region/{RegionId}/Links` | 获取指定区域的关联知识图谱节点（分页）。 | `partial_truncated` (200) · S32 | unparsed; RegionLinksResponse |
| `GET /api/Map/Region/{RegionId}/OutsideOfficials/{Dynasty}` | 获取指定区域（及可选朝代过滤）的外地官员（在此区域任职的外来人员）统计明细CSV文件。 | `partial_truncated` (200) · S33 | unparsed |
| `GET /api/Map/Region/{RegionId}/Officials/{Dynasty}` | 获取指定区域（及可选朝代过滤）的本地官员统计明细CSV文件。 | `partial_truncated` (200) · S34 | unparsed |
| `GET /api/Map/Scenery/{RegionId}/{Name}/Links` | 获取指定景点的关联知识图谱节点（分页）。 | `partial_truncated` (200) · S35 | unparsed; SceneryLinksResponse |
| `GET /api/Map/Scenery/{key}` | 按关键字或 Id 搜索景点（模糊匹配或精确 Id），不返回详情正文。 | `valid_shape` (200) · S36 | array |
| `GET /api/Map/Scenery/{RegionId}/{Name}` | 获取指定景点的详细信息（含简介、正文与关联链接计数）。 | `valid_shape` (200) · S37 | Province、City、Name、Latitude、Longitude、Aliases、Links、Summary、Detail; SceneryDetailDto |

#### Swagger / Mcp

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `POST /mcp` |  | `not_tested` · S38 | — |
| `POST /api/mcp` |  | `not_tested` · S39 | — |

#### Swagger / People

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/People` | 获取人物总量及各主/次时间线（朝代）对应人物数量统计。 | 参见 P 实例 | —; PeopleStatResponse |
| `GET /api/People/{id}` | 按输入标识获取： 1. 数字 → 指定人物详请；2. 朝代键 → 对应朝代人物列表；3. 解析姓名/别名 → 人物详请。 | `valid_shape` (200) · S40 | Person、Links; DynastyPeopleListResponse |
| `GET /api/People/{id}/MapInfo` | 获取人物地理（籍贯 / 活动）映射视图数据。 | `valid_shape` (200) · S41 | Markers、Center、ZoomLevel |
| `GET /api/People/{id}/Mentionship` | 获取人物“述及 / 被述及”关系概览CSV文件。 | `unexpected_response` (200) · S42 | non_json |
| `GET /api/People/{id}/Mentionship/{targetId}` | 获取“述及”作品列表（某人物针对另一人物的引用作品，分页）。 | `http_error` (404) · S43 | Message; MentionshipWritingListResponse |
| `POST /api/People/Find` | 综合查询（姓名 / 区域 / 朝代）。支持区域歧义、区域人物、人物列表多种返回。 | 参见 P 实例 | —; PeopleListResponse |

#### Swagger / Poem

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Poem/{id}` | 根据作品 Id 获取诗作（可选附带知识图谱链接）。 | `valid_shape` (200) · S44 | Id、Classes、GroupIndex、Froms、Allusions、Pictures、Dynasty、Author、AuthorId; Shi |
| `GET /api/Poem/{id}/MapInfo` | 获取诗作的地域标注与地域关联视图（MapInfo）。 | `valid_shape` (200) · S45 | PoemId、RegionView; PoemMapInfoResponse |
| `GET /api/Poem/{id}/BookLinks` | 分页获取诗作在典籍资源中的引用 / 链接（刊佚 / 版本 / 对勘来源）。 | `valid_shape` (200) · S46 | PoemId、PageNo、Data; PoemBookLinksResponse |
| `GET /api/Poem/SimilarClauses/{key}` | 查找与给定诗句或指定诗作全部句子相似的其他作品诗句。 | `valid_shape` (200) · S47 | array |
| `GET /api/Poem/SameRhymes/{key}` | 按韵脚序列匹配与指定作品或输入韵脚序列同韵的作品集合。 | `valid_shape` (200) · S48 | array |

#### Swagger / QuTune

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/QuTune` | 获取全部曲牌的基础信息（不包含格式定义）。 | 参见 P 实例 | — |
| `GET /api/QuTune/{tuneId}/{formatIndex}` | 获取指定曲牌详情；可指定格式索引返回单一曲谱格式。 | `valid_shape` (200) · S49 | Id、Name、Format; QuTuneSingleFormatResponse |
| `GET /api/QuTune/{tuneId}/Writings` | 获取指定曲牌的例作品（按朝代分类聚合）。 | `valid_shape` (200) · S50 | Id、Name、Writings; QuTuneWritingsResponse |
| `POST /api/QuTune/Find` | 通过关键词（名称或别名，支持繁简统一）检索曲牌（不含格式）。 | 参见 P 实例 | — |

#### Swagger / Rhyme

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Rhyme` | 获取支持的韵书名称列表。 | 参见 P 实例 | —; RhymeBooksResponse |
| `GET /api/Rhyme/{book}` | 按韵书获取全部韵部分类。 | `valid_shape` (200) · S51 | Book、Categories; TongYunBookCategoriesResponse |
| `GET /api/Rhyme/{book}/{category}` | 按韵书与韵部名称获取韵部详情（含映射 / 字表 / 归属差异）。 | `valid_shape` (200) · S52 | Book、Categories; RhymeBookCategoryDetailResponse |
| `GET /api/Rhyme/{book}/{category}/{character}` | 按韵书 + 韵部 + 单字查询其归属与同韵信息。 | `http_error` (404) · S53 | Message; RhymeCharResponse |
| `POST /api/Rhyme/Find` | 通用查询（模型中可提供：书名 / 韵部 / 字）。 | 参见 P 实例 | —; RhymeCharResponse |

#### Swagger / SilkRoad

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/SilkRoad` | 获取丝绸之路行旅总览数据（含多个线路 Traces 及公共信息）。 | `partial_truncated` (200) · S54 | unparsed; TravelTraceData |
| `GET /api/SilkRoad/{id}` | 按线路标题获取该线路的详细标注点视图。 若未匹配到指定标题，则返回空标题与默认中心/缩放（0 值），Markers 为全量 DetailView。 | `partial_truncated` (200) · S55 | unparsed; TravelTraceData |

#### Swagger / Tool

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `POST /api/Tool/CharsetConvert` | 繁简转换接口。 | 参见 P 实例 | —; CharsetConvertResponse |
| `POST /api/Tool/Label` | 文本標簽化（實體抽取 / 知识链接抽取）。 | `valid_shape` (200) · S56 | Subject、Content、SubjectLabels、ContentLabels、Entities; LabelingResponse |
| `POST /api/Tool/LabelAndResolveEntity` | 文本標簽化（實體抽取 / 知识链接抽取）兼返回實體詳細資料。 | `valid_shape` (200) · S57 | Subject、Content、SubjectLabels、ContentLabels、Entities; LabelingResponse |
| `POST /api/Tool/Reference` | 句子出處與化用 / 引用檢測。 | 参见 P 实例 | —; ReferenceResponse |
| `POST /api/Tool/Texting` | 文本快速解析 / 助手接口（輸入文本 → 解析 HTML）。 | 参见 P 实例 | —; TextingResponse |
| `POST /api/Tool/AnalyzePoem` | 律詩校驗接口。對輸入詩作進行平仄、押韻、句式等規則校驗並返回結構化結果。 | `network_error` · S58 | —; PoemAnalyzeResultWithSuggestion |
| `POST /api/Tool/AnalyzeCi` | 词作格律校验接口。对输入词作按照词牌规则进行平仄、押韵、句式等校验并返回结构化结果。 | `valid_shape` (200) · S59 | ErrorMessage、Notification、QinPuValidationResult、LongPuValidationResult; CiAnalyzeResultWithSuggestion |
| `POST /api/Tool/AnalyzeCouplet` |  | `valid_shape` (200) · S60 | MultiSpells、UncertainTones、Clauses、ErrorMessage; CoupletValidationResult |

#### Swagger / WeChat

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/WeChat/Message/{text}` | 直接以明文方式查询（绕过微信服务器），用于调试或独立调用。 | `not_tested` · S61 | — |
| `POST /api/WeChat` | 处理来自微信服务器的消息推送。 支持：订阅事件（返回欢迎语）与文本 / 链接消息（进入查询逻辑）。 | `not_tested` · S62 | — |
| `GET /api/WeChat` | 微信服务器配置校验接口（首次接入 / 每次修改服务器地址时调用）。 | `not_tested` · S63 | — |

#### Swagger / Writing

| 方法与路径 | 官方用途摘要 | 首轮状态 | 返回结构 / Schema |
| --- | --- | --- | --- |
| `GET /api/Writing` | 獲取全站作品總量與各朝代作品/作者統計匯總。 | 参见 P 实例 | —; WritingStatisticsDto |
| `GET /api/Writing/{id}` | 根據輸入 Id / 名稱 / 朝代鍵進行解析： 1. 若為可識別朝代且允許簡化 → 返回該朝代作者分佈； 2. 若為數字 → 視為作品 Id； 3. 否則視為作者名稱模糊搜索。 | `valid_shape` (200) · S64 | Writing、Links; WritingWithLinksDto |
| `GET /api/Writing/{dynasty}/{author}/{authorId}/{writingType}` | 按（朝代 + 作者 + 可選作者 Id）導出指定作者作品列表CSV文件（可篩選作品類型）。 | `http_error` (400) · S65 | errors、type、title、status、traceId |
| `GET /api/Writing/{id}/MapInfo` | 獲取作品地域標註視圖（MapInfo）。 | `unexpected_response` (204) · S66 | non_json |
| `GET /api/Writing/{id}/BookLinks/Export` | 導出與指定作品（或輸入單句）相似的詩句集合到CSV文件。 | `not_tested` · S67 | — |
| `GET /api/Writing/{id}/BookLinks` | 分頁獲取作品在典籍 / 勘校資源中的引用鏈接。 | `valid_shape` (200) · S68 | Froms、ResourceType、ResourceId、Count、PageSize、PageNo、Links |
| `GET /api/Writing/{id}/CreatedGlossary` | 獲取指定作品創造或首用的典故及詞彙 | `valid_shape` (200) · S69 | WritingId、Allusions、Words; CreatedGlossaryDto |
| `GET /api/Writing/SimilarClauses/{key}` | 查找與指定作品（或輸入單句）相似的詩句集合。 | `unexpected_response` (302) · S70 | non_json |
| `GET /api/Writing/SameClausePattern/{writingId}/{clauseIndex}` | 查找與輸入句子相同的詩句集合。 | `network_error` · S71 | —; ClauseResultDto |
| `GET /api/Writing/SameClausePattern/{clause}` | 查找與輸入句子相同的詩句集合。 | `network_error` · S72 | —; ClauseResultDto |
| `GET /api/Writing/SimilarClauses/{key}/Export` | 導出與指定作品（或輸入單句）相似的詩句集合到Csv文件。 | `not_tested` · S73 | — |
| `GET /api/Writing/SameRhymes/{key}` | 查找與指定作品或韻腳序列同韻的作品集合。 | `valid_shape` (200) · S74 | array |
| `GET /api/Writing/SameRhymes/{id}/Export` | 將與指定作品同韻的作品導出為 CSV 文件。 | `not_tested` · S75 | — |
| `GET /api/Writing/FollowedRhymes/{id}/Export` | 將指定作品的跨世步韻作品導出為 CSV 文件。 | `not_tested` · S76 | — |
| `GET /api/Writing/Couplet/{id}` | 查詢含指定對語（對仗詞組）的詩句示例。 | `http_error` (404) · S77 | Value、Formatters、ContentTypes、DeclaredType、StatusCode; CoupletResultDto |
| `GET /api/Writing/Export` | 導出指定搜索上下文的作品（最多 6000 首）。 | `not_tested` · S78 | — |
| `POST /api/Writing/Export` | 導出指定搜索上下文的作品（最多 6000 首）。 | `not_tested` · S79 | — |
| `GET /api/Writing/Export/Text` | 將指定搜索上下文的作品導出為純文本（最多 6000 首）。 | `not_tested` · S80 | — |
| `POST /api/Writing/Find` | 綜合搜尋接口：支持關鍵詞 / 作者 / 韻部 / 標簽等復合條件。 | 参见 P 实例 | —; WritingSearchResultDto |
| `GET /api/Writing/{id}/Tones` | 獲取作品的句內字聲調（平仄）標註。 | `valid_shape` (200) · S81 | Writing、ClauseTones; WritingTonesDto |
| `GET /api/Writing/{id}/Labeling` | 獲取作品的標簽（知識鏈接）結果。 | `valid_shape` (200) · S82 | Writing、Links; WritingLabelingDto |
| `GET /api/Writing/Author/{authorId}/{region}/{name}` | 獲取作者在某一地域（或地域下某景點）相關的作品聚合（地圖視圖）。 | `http_error` (404) · S83 | Value、Formatters、ContentTypes、DeclaredType、StatusCode; TravelTraceData |
| `GET /api/Writing/HasLabel` | 判斷是否存在包含指定標簽的作品，如有，以CSV文件方式返回具體數據。 | `http_error` (400) · S84 | str |
| `GET /api/Writing/UsedByCento/Author/{authorId}` | 查詢某作者作品中被後世詩文（集句 / 摭拾）引用的句子（Cento）。 | `partial_truncated` (200) · S85 | unparsed; UsedByCentoResultDto |

### B. Postman 原始示例记录（71 项）

这里**保留同一路由不同输入的全部示例**，以免后来忘记本来有多种查询形式。‘响应字段’只是这一条输入返回的首层 JSON 键（截断和异常时为空）。

#### Postman / 人物

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P01 | `GET /api/people` | 人物总览；`{}` | `valid_shape` (200) | Total、Dynasties |
| P02 | `GET /api/people/{{dynasty}}` | 按朝代浏览；`{}` | `http_error` (404) | Message |
| P03 | `GET /api/people/15188` | 获取特定人物介绍；`{}` | `partial_truncated` (200) | unparsed |
| P04 | `POST /api/people/find` | 搜索符合指定籍贯与生卒时间范围的人物；`{"scope":"HomeTown","key":"潮州市","begin":920,"end":1520}` | `valid_shape` (200) | People |
| P05 | `POST /api/people/find` | 按姓氏搜索人物列表；`{"scope":"Xing","key":"司马"}` | `valid_shape` (200) | People |
| P06 | `POST /api/people/find` | 按谥号搜索人物列表；`{"scope":"ShiHao","key":"文正"}` | `valid_shape` (200) | People |

#### Postman / 古籍库

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P07 | `GET /api/book` | 获取古籍库总览；`{}` | `valid_shape` (200) | Total、Categories |
| P08 | `GET /api/book/史部/正史类` | 获取某一分类下详细书目；`{}` | `valid_shape` (200) | Category、Group、Books |
| P09 | `GET /api/book/2180` | 获取某一部书的详细信息；`{}` | `valid_shape` (200) | Book |
| P10 | `GET /api/book/volume/KR4h0140_024` | 获取某一卷详细内容；`{}` | `valid_shape` (200) | VolumeId、Text、Html |
| P11 | `POST /Api/Book/Find` | 按关键词搜索古籍库；`{"key":"黄鹤楼","pageNo":1}` | `valid_shape` (200) | Count、PageSize、Key、PageNo、Notification、Summary、Result、Error |
| P12 | `POST /Api/Book/Find` | 检索古籍库时在关键词中使用问号通配符；`{"key":"黄鹤？楼"}` | `valid_shape` (200) | Count、PageSize、Key、PageNo、Notification、Summary、Result、Error |
| P13 | `POST /Api/Book/Find` | 检索同时包含多个关键词的古籍；`{"key":"黄鹤楼 鹦鹉洲"}` | `valid_shape` (200) | Count、PageSize、Key、PageNo、Notification、Summary、Result、Error |

#### Postman / 地理

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P14 | `GET /api/map/region` | 行政区划总览；`{"regionId":"CN11","regionName":"潮州市"}` | `valid_shape` (200) | array |
| P15 | `GET /api/map/region/{{regionId}}` | 按 Id 查询某一行政区划及其下级区划的信息；`{"regionId":"CN11","regionName":"潮州市"}` | `valid_shape` (200) | array |
| P16 | `GET /api/map/region/{{regionName}}` | 按名称查询某一行政区划及其下级区划的信息；`{"regionId":"CN11","regionName":"潮州市"}` | `valid_shape` (200) | array |
| P17 | `GET /api/map/region/{{regionId}}/links` | 查询与某一行政区划相关的链接；`pageNo=0` | `partial_truncated` (200) | unparsed |
| P18 | `GET /api/map/scenery/{{regionId}}` | 查询某一行政区划下有哪些景观；`{"regionId":"CN11","regionName":"潮州市"}` | `partial_truncated` (200) | unparsed |
| P19 | `GET /api/map/scenery/CN3301/西湖` | 查询某一景观的详细信息；`{"regionId":"CN11","regionName":"潮州市"}` | `valid_shape` (200) | Province、City、Name、Latitude、Longitude、Aliases、Links、Summary、Detail |
| P20 | `GET /api/map/scenery/CN4201/黄鹤楼/links` | 查询某一景观的相关链接；`pageNo=0` | `partial_truncated` (200) | unparsed |

#### Postman / 字典

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P21 | `GET /api/char/中` | 查字；`{}` | `valid_shape` (200) | ModernDictionary、KangXiDictionary、ShuoWenDictionary |

#### Postman / 工具

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P22 | `POST /api/tool/charsetConvert` | 简体转繁体；`{"content":"白发惊看镜里秋","mode":"ToTraditional"}` | `valid_shape` (200) | ConvertedContent、CharOptionExplanations |
| P23 | `POST /api/tool/charsetConvert` | 繁体转简体；`{"content":"暫到此中閒","mode":"ToSimplified"}` | `valid_shape` (200) | ConvertedContent、CharOptionExplanations |
| P24 | `POST /api/tool/labelize` | 自动笺注；`{"content":"<text:303 chars>","dynasty":"北齐"}` | `http_error` (404) | non_json |
| P25 | `POST /api/tool/reference` | 出处与化用分析；`{"content":"<text:64 chars>"}` | `valid_shape` (200) | Sentences |
| P26 | `POST /api/tool/texting` | 短信息查询；`{"content":"乾隆三年正月甲子，乾隆帝……"}` | `valid_shape` (200) | Html |

#### Postman / 年历

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P27 | `GET /api/calendar` | 总览；`{}` | `valid_shape` (200) | Dynasties |
| P28 | `GET /api/calendar/{{dynasty}}` | 按朝代浏览；`{}` | `valid_shape` (200) | Name、Dynasties |
| P29 | `GET /api/calendar/eraYear/宋绍兴` | 查看某一年号详细信息；`{}` | `valid_shape` (200) | Id、Name、GovernBeginTime、GovernEndTime、AuthorId、EraYears |
| P30 | `GET /api/calendar/date/901年` | 查某一年；`{}` | `valid_shape` (200) | Date、EraYears、Links、ShuoLeapTable |
| P31 | `GET /api/calendar/date/宋绍兴五年七月丁酉` | 查某一日期；`{}` | `valid_shape` (200) | Date、EraYears、Links、ShuoLeapTable |
| P32 | `GET /api/calendar/GanZhi/庚子` | 查历代某一干支年；`{}` | `partial_truncated` (200) | unparsed |
| P33 | `GET /api/calendar/date/901年/links` | 查询与某一时间相关的链接；`pageNo=0` | `partial_truncated` (200) | unparsed |

#### Postman / 曲谱

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P34 | `GET /api/quTune` | 曲谱总览；`{}` | `partial_truncated` (200) | unparsed |
| P35 | `GET /api/quTune/90` | 查询特定曲谱；`{}` | `valid_shape` (200) | Formats、Id、Name、Path、Aliases、NameComment、WritingCount |
| P36 | `GET /api/quTune/1/writings` | 查询历代使用指定曲谱的作品；`{}` | `valid_shape` (200) | Id、Name、Writings |
| P37 | `POST /api/quTune/find` | 搜索名称含某一关键词的曲谱；`{"key":"春"}` | `valid_shape` (200) | array |

#### Postman / 类书

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P38 | `GET /api/category` | 获取类书列表；`{}` | `valid_shape` (200) | Books |
| P39 | `GET /api/category/钦定古今图书集成` | 获取某一本类书的目录结构；`{}` | `partial_truncated` (200) | unparsed |
| P40 | `GET /api/category/钦定古今图书集成/0002/KR7a0001_018` | 获取古今图书集成某一条目某一卷的详细内容；`{}` | `partial_truncated` (200) | unparsed |
| P41 | `GET /api/category/渊鉴类函/0024` | 获取渊鉴类函某一条目的详细内容；`{}` | `valid_shape` (200) | Id、Name、Alias、Note、VolumeIds、Content、ImageUrls |
| P42 | `GET /api/category/方舆胜览/0012` | 获取方舆胜览某一条目详细内容；`{}` | `valid_shape` (200) | Id、Name、Alias、Note、VolumeIds、Content、ImageUrls |
| P43 | `POST /api/category/find` | 查询含某一关键词的条目；`{"key":"潮州"}` | `valid_shape` (200) | array |

#### Postman / 词汇、典故

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P44 | `GET /api/glossary/词典/10` | 按词汇 Id 查询；`{}` | `valid_shape` (200) | Word、OriginalWord、From、Spellings、Explains、Categories、Kind、Id |
| P45 | `GET /api/glossary/典故/1000` | 按典故 Id 查询；`{}` | `valid_shape` (200) | CountInWritings、Keys、RelatedPersons、Correlations、References、Quotes、Explains、Kind、Id |
| P46 | `GET /api/glossary/佛典/100` | 按佛典 Id 查询；`{}` | `valid_shape` (200) | Word、OriginalWord、From、Spellings、Explains、Categories、Kind、Id |
| P47 | `POST /api/glossary/词典` | 按词典 Id 批量查询；`[10]` | `valid_shape` (200) | array |
| P48 | `POST /api/glossary/典故/find` | 按关键词查询典故；`{"key":"桃花","charIndex":"end"}` | `valid_shape` (200) | array |

#### Postman / 词谱

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P49 | `GET /api/ciTune` | 词谱总览；`{}` | `partial_truncated` (200) | unparsed |
| P50 | `GET /api/ciTune/90` | 查询特定词谱；`{}` | `valid_shape` (200) | Formats、Id、Type、Name、Aliases、Desc、WritingCount |
| P51 | `GET /api/ciTune/1/writings` | 查询历代使用指定词谱的作品；`{}` | `valid_shape` (200) | Id、Name、Writings |
| P52 | `POST /api/ciTune/find` | 搜索含某一关键词的词谱；`{"key":"月"}` | `valid_shape` (200) | array |
| P53 | `POST /api/ciTune/pattern` | 查询哪些词牌含有与输入句子平仄结构相同的片段；`{"pattern":"对潇潇暮雨洒江天"}` | `valid_shape` (200) | Pattern、MatchedLength、MatchedTuneFormats |

#### Postman / 诗文库

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P54 | `GET /api/writing` | 总览；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Total、Dynasties |
| P55 | `GET /api/writing/{{dynasty}}` | 按朝代浏览；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Key、Dynasties |
| P56 | `GET /api/writing/{{dynasty}}/{{authorName}}/{{authorId}}/{{writingType}}` | 按作家浏览；`pageNo={{pageNo}}` | `http_error` (400) | errors、type、title、status、traceId |
| P57 | `GET /api/writing/{{writingId}}` | 获取特定作品；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Writing、Links |
| P58 | `GET /api/writing/{{writingId}}` | 获取特定作品，返回结果不作繁简转换；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Writing、Links |
| P59 | `GET /api/writing/couplet/{{coupletWords}}` | 获取含特定对仗词汇组的律句；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Word1、Word2、Couplets |
| P60 | `POST /api/writing/find` | 组合搜索；`{"key":"八景","exactlyMatch":true,"clauseIndex":"title"}` | `valid_shape` (200) | Notification、WritingCount、PageNo、PageSize、MatchedKeys、Writings |
| P61 | `GET /api/writing/SimilarClauses/{{key}}` | 获取作品库中有相似句子的作品；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `unexpected_response` (302) | non_json |
| P62 | `GET /api/writing/SameRhymes/{{key}}` | 获取作品库中与指定作品所押韵脚相同的作品；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | array |
| P63 | `GET /api/writing/{{writingId}}/tones` | 为作品标注平仄；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Writing、ClauseTones |
| P64 | `GET /api/writing/{{writingId}}/bookLinks` | 获取作品在古籍库中的出处及引用信息；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `valid_shape` (200) | Froms、ResourceType、ResourceId、Count、PageSize、PageNo、Links |
| P65 | `GET /api/writing/{{writingId}}/labelize` | 自动笺注；`{"authorId":"17270","authorName":"杜甫","writingId":"10000","coupletWor…` | `http_error` (406) | non_json |
| P66 | `POST /api/writing/find` | 查询符合某一平仄句式的律句；`{"key":"中平中仄仄平平"}` | `valid_shape` (200) | Notification、WritingCount、PageNo、PageSize、MatchedKeys、WritingSentences |

#### Postman / 韵典

| 编号 | 方法与路径 | 示例用途 / 输入 | 首轮状态 | 响应字段 |
| --- | --- | --- | --- | --- |
| P67 | `GET /api/rhyme` | 总览；`{}` | `valid_shape` (200) | Books |
| P68 | `GET /api/rhyme/平水韵` | 获取某一韵书韵目信息；`{}` | `valid_shape` (200) | Book、Categories |
| P69 | `GET /api/rhyme/平水韵/青` | 获取某一韵目字表；`{}` | `valid_shape` (200) | Book、Categories |
| P70 | `GET /api/rhyme/平水韵/侵/参` | 获取韵字详细信息；`{}` | `valid_shape` (200) | Char、Comment、Sames、Spellings、WordStartsWith、WordEndsWith、ReferToPeiWenYunFu、ReferToChars、Writi… |
| P71 | `POST /api/rhyme/find` | 查某字在某一韵书中的信息；`{"Character":"冠","Book":"平水韵"}` | `partial_truncated` (200) | unparsed |

### C. 阅读索引注意事项

- Swagger 的模板参数（如 {id}）和 Postman 的真实示例 ID 可能只是在文本上不同；不能按 105+71 推算出独立能力总数。
- 在追查某条接口时先按 P/S 编号打开 HTML，确认真正提交的 test_path、请求体、HTTP 状态、采样上限、响应结构和失败原因。PDF/CSV/导出接口并没有因此获得授权。
- 需要更新 Swagger 或 Postman 时先比较原始 SHA，再保存新快照。这份索引由本地已归档的清单生成，不自动联系 CNKGraph。

<!-- END GENERATED API MATRIX -->
