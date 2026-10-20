# Poeticus Roadmap

> 更新日期：2026-10-20
>
> 当前状态：v0.6.0 已发布。首页入场与搜索过渡、桌面 / iPad 竖排居中、原文引用下划线和统一中国红已进入主线；公开阅读、Agent、AI Eval 和 Poem Retrieval 保持既有线上链路。Document Corpus 已在本地使用 PostgreSQL/pgvector 和可选 `search_documents`；**2026-10-20 私有数据增至六书、1152 节/向量**，但正式四书导入 CLI 尚未支持这次增量，也未公开部署。LangGraph 新增的 CNKGraph 研究、DeepSeek Search/Fetch、萌典/维基文库研究工具**代码已入 main，均默认关闭**，不能当作线上已验收功能。检索服务仍依赖按需运行的 WSL / Cloudflare Tunnel。

Roadmap 只记录下一阶段方向。已经完成的实现过程留在 Release、devlog 和 ADR；具体任务继续进入 GitHub Issues。

## 1. 当前基线

Poeticus 已经走通：

- React / TypeScript / Vite 阅读界面；
- 首页竖排每日一词与馆藏搜索（日期稳定推荐，公开词库 3491 首）；
- 阅读页桌面双栏、动态目录分页和手机／桌面独立布局外壳；
- 手机、平板、桌面响应式阅读 / 讨论工作区；
- FastAPI 同源后端；
- PostgreSQL 公开作品库与 3491 首词作；
- 私人 EPUB → JSON → 私人 DB → 公网 DB 的数据链；
- LangGraph ReAct Agent；
- CNKGraph 典故 / reference evidence；
- bounded multi-turn context；
- SSE 流式回答；
- localStorage Conversation persistence；
- Railway 公网部署；
- Seed AI Eval 与 Retrieval Increment Eval；
- Werneror 853,385 Work Retrieval Corpus；
- Qwen sentence + clause Dense Retrieval；
- character 2-3 gram + BM25；
- deterministic Query Plan；
- Work-level RRF；
- chronology Candidate Eligibility；
- 组诗重复拼接关系查表过滤（PR #286、已关闭 #151）；
- FAISS IVFPQ Serving；
- 独立 Text Retrieval HTTP Service；
- WSL CPU Retrieval Serving + Cloudflare 命名 Tunnel（原腾讯云 2C8G 节点已销毁）；
- Railway Agent → HTTPS → Retrieval → candidate → final answer 的真实 E2E。

Retrieval 的阶段性目标已经达到。后续不继续围绕 FAISS 参数、更多 Chunk、更多 sparse ranking 变体做惯性扩张。

## 2. 近期事项

### 2.1 阅读交互与 iOS 选区

- [#86](https://github.com/montricwang/poeticus/issues/86)：iPhone 原文长按及拖柄调整选区时，引用卡片与阅读区红色下划线应及时同步到最终选区；结合 Safari 真机事件时序排查。
- [#294](https://github.com/montricwang/poeticus/issues/294)：继续收集极端手机尺寸、横屏及系统键盘场景的排版反馈；日常字号与竖排规则以[现行设计规范](design/frontend-visual-conventions.md)为准。

### 2.2 Production hygiene

当前部署是 Railway Web/Agent + Cloudflare 命名 Tunnel + WSL Retrieval，不再维护已销毁腾讯云节点的公网 IP 证书、Nginx 或 2C8G 扩容规划。

- [#151](https://github.com/montricwang/poeticus/issues/151) 已完成：Werneror 的完整拼接自我重复由关系表过滤，并在正式页面验收；少量异文和不完整拼接依约留待真实 Case。
- 当前运维重点是 WSL CPU Serving 和 Windows `cloudflared` 的重启恢复、Bearer 鉴权、Railway ↔ Tunnel 的真实可用性及错误降级（[#180](https://github.com/montricwang/poeticus/issues/180)）。
- 未来确有长期可用性或流量需求，再考虑独立云主机、性能基线、容量及必要的 Retrieval CI/CD。

### 2.3 工程基础补课

#166 单独安排一堂简短课程，用本次生产数据讲：

- database / artifact / index；
- CPU / RAM / disk；
- FAISS 大小和资源影响；
- cold / warm；
- process / port / health；
- reverse proxy / HTTPS / token；
- service-to-service communication；
- 服务器规格判断。

这一轮的目标是把最近几天大量局部判断重新整理成稳定系统图。

### 2.4 AI Evaluation

当前已经有 Seed Eval、Retrieval Increment Case、真实 Agent E2E。

下一步更值得补：

- Tool routing regression；
- Retrieval candidate 可见但 Agent 选错的 Case；
- query reformulation 的成功 / 失败样本；
- 多轮上下文与工具调用共同出现时的回归；
- Prompt / 模型更新后的稳定性比较。

单元测试、AI Eval、Trace、生产 E2E 继续分层。

### 2.5 Corpus quality

公开阅读数据仍保留 `imported_unreviewed` 状态。

近期继续：

- 修 EPUB 结构误判；
- 补小序、注释、寓声、缺文等 regression sample；
- 建立 curated correction 与原始抽取之间的明确边界；
- 逐步补充可靠年代 metadata，而不把 Werneror coarse dynasty 回写成阅读库事实。

### 2.6 UX reliability

真实设备问题继续按 Issue 推进：

- iOS 选区；
- 长对话可读性；
- SSE 中断 / 重试体验；
- 目录与阅读区细节；
- 赏析和对话之间的切换。

10 月 15 日已合并桌面阅读版心与目录改进（PR #291）、手机／桌面布局外壳拆分（PR #292）及首页推荐和馆藏搜索（PR #293）；10 月 16 日合并 Safari 竖排修复（PR #295）与每日一词（PR #297）。iPhone Safari 在不同视口下的断行差异仍由 [#294](https://github.com/montricwang/poeticus/issues/294) 跟进。首页信息架构 [#113](https://github.com/montricwang/poeticus/issues/113) 还有作者入口、导航与阅读进度等待设计和实现。

### 2.7 诗学画像与推荐（研究阶段）

[#156](https://github.com/montricwang/poeticus/issues/156)／[#157](https://github.com/montricwang/poeticus/issues/157) 的 3491 首词双模型实验见 [10 月 14 日开发日志](devlog/2026-10-14.md) 和 [聚类复现实验](../scripts/experiments/README-clustering.md)。BERT-CCPoem 与 Qwen3 Embedding 的无监督 K-means 分组没有得到可直接命名的稳定文学风格，**不接生产推荐或自动贴标签**。

下一步先选 50–100 首典型与反例，分别论证题材／情感、意象、可举证写法与传统审美术语的文本证据和标注一致性；近邻是否有助于真实阅读由人工判断，暂不因已有向量就训练分类器。

## 3. 下一批能力候选

Retrieval 已经可以作为一个完成度较高的求职能力面。下一阶段更适合补新的横向能力。

### Curated literature RAG

候选方向：

- 词话；
- 诗话；
- 历代评论；
- 可靠作者生平 / 编年资料。

已在本地用六部词学文献构建结构化 Document Corpus 与 Hybrid/Agentic 查询实验；其中首批四书可由仓库 CLI 重建，新增两书是私有专项导入。下一步按 [#343](https://github.com/montricwang/poeticus/issues/343) 修复《蕙風詞話》缺字和《介存齋論詞雜著》正文边界，完成六书可复现性，再根据实际收益考虑 10、20、40 部的规模实验；按 [#344](https://github.com/montricwang/poeticus/issues/344) 建立约 100 题、含独立 holdout 的证据评测集。逐步验证：

```text
问题类型
→ domain routing
→ curated retrieval
→ source-grounded answer
```

Document Corpus 与实时业务数据继续分开。订单、库存、余额一类实时状态应走 API / DB Tool。

接入新语料或工具前，先查看 [数字人文资源地图](digital-humanities-resources.md)，用 [#184](https://github.com/montricwang/poeticus/issues/184) 验证已有开放数据 / API / 方法是否能替代自行采集、整理或新建系统的工作；未核查权限与增量价值的来源不直接进入生产。

### Search / Web fallback

2026-10-20 已把 **DeepSeek Search/Fetch** 以默认关闭的本地研究工具合入 `main`，另提供维基文库官方搜索/单页读取、CNKGraph 古籍短查询等专门工具；**不意味着已启用公众联网问答**。下一步依 [#364](https://github.com/montricwang/poeticus/issues/364)、[#355](https://github.com/montricwang/poeticus/issues/355) 检查权限、成本、来源安全、Tool routing、真实 Agent 答案与退化；只在这些来源对具体问题有可验证增益时考虑开启。

### Multi-span evidence

当前 Retrieval Tool 主要围绕一段文本。全文多线索可继续探索：

```text
多个 span 独立召回
→ Work / source 级证据聚合
→ 必要时二次检索
```

这项工作等真实全文 Case 提供明确增量再开。

### Critic 的人格、知识与记忆（研究阶段；不阻塞当前发布）

- **已存在**：Persona / Skills / Library / Notebook 的边界设计 [#148](https://github.com/montricwang/poeticus/issues/148)，Critic 独立判断/文风优先级 [#311](https://github.com/montricwang/poeticus/issues/311)，有据可查的批评方法提炼研究 [#354](https://github.com/montricwang/poeticus/issues/354)。
- **已做但仅限原型**：[PR #348](https://github.com/montricwang/poeticus/pull/348) 的追加式 SQLite 观点事件原型（未合并、未接在线 Agent）；[#347](https://github.com/montricwang/poeticus/issues/347) 计划对比 LangMem / Mem0 / Hindsight 等成熟方案。它们**不能被标成已上线长期记忆**。
- **下一步需要讨论，而非已确定实现**：三轴知识模型（保存的内容/数据结构/运行时调用）、从私有访谈材料抽取的创始人审美种子、可选 MAGI 式考据/审美/反证三视角。优先 3–5 段真实文献的提炼质量 [#341](https://github.com/montricwang/poeticus/issues/341)，再做隔离 Bootstrap [#312](https://github.com/montricwang/poeticus/issues/312) 和独立 Eval [#314](https://github.com/montricwang/poeticus/issues/314)；不预设三 Agent、模型微调、图数据库或自动修改 Persona。

## 4. Retrieval 当前停止线

以下内容暂时不进入主线：

- pq512；
- clause BM25；
- reranker / Cross-Encoder（Poem Retrieval 仍为 #119 离线待评；Document RAG 已有可选本地实验代码，16 题效果尚不支持默认启用）；
- learned sparse；
- LTR；
- 全局同义词 / 意象扩展；
- 专门古汉语分词工程；
- 多 worker；
- GPU Serving；
- Kubernetes；
- Corpus pruning #163。

重新打开的条件很简单：真实产品 Case 稳定失败，而且失败能明确指向其中某一层。

## 5. 求职与学习目标

一个技术点准备写进简历前，至少满足：

> 做过 → 遇到过问题 → 能解释为什么这样做，以及没有这样做会怎样。

v0.5.0 沿用的检索链路应能讲清楚（原腾讯云 VPS 已销毁）：

```text
Frontend（Railway Web）
→ FastAPI / LangGraph Agent
→ Tool routing / HTTP Retrieval Client
→ HTTPS / Cloudflare Tunnel
→ WSL CPU Poem Retrieval Service（按需启动）
→ Query Plan / FAISS Dense + BM25 Sparse
→ Work-level RRF / Chronology Eligibility
→ Werneror 重复合集过滤
→ Evidence 回传 / Agent 输出
→ 网站上的实际提问与验证
```

接下来学习重点从“再多做一个 Retrieval 组件”转向：

- 把已经做过的系统讲清楚；
- 补服务器 / 数据库 / 服务通信的基础心智模型；
- 增加新的能力面；
- 保留真实 Eval 和生产证据。

## 6. 开发停止线

每个阶段继续沿用：

1. 明确问题；
2. 做最小真实闭环；
3. 运行并观察；
4. 记录取舍；
5. 安排一次消化；
6. 再决定下一层。

长期原则：

> **原理必须理解，判断必须参与，执行可以委托。**

> **复杂度由真实失败购买。**