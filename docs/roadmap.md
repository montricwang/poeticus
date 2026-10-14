# Poeticus Roadmap

> 更新日期：2026-10-14
>
> 当前状态：v0.4.0 公网版；公开阅读、Agent、AI Eval 与 Poem Retrieval 已具备真实线上链路。2026-10-14 完成 Werneror 拼接关系去重与正式站点验收；WSL/Tunnel 是按需运行的检索依赖，而不是已迁往云端的常驻节点。

Roadmap 只记录下一阶段方向。已经完成的实现过程留在 Release、devlog 和 ADR；具体任务继续进入 GitHub Issues。

## 1. 当前基线

Poeticus 已经走通：

- React / TypeScript / Vite 阅读界面；
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

## 2. v0.4.0 之后的近期事项

### 2.1 Production hygiene

当前部署是 Railway Web/Agent + Cloudflare 命名 Tunnel + WSL Retrieval，不再维护已销毁腾讯云节点的公网 IP 证书、Nginx 或 2C8G 扩容规划。

- [#151](https://github.com/montricwang/poeticus/issues/151) 已完成：Werneror 的完整拼接自我重复由关系表过滤，并在正式页面验收；少量异文和不完整拼接依约留待真实 Case。
- 当前运维重点是 WSL CPU Serving 和 Windows `cloudflared` 的重启恢复、Bearer 鉴权、Railway ↔ Tunnel 的真实可用性及错误降级（[#180](https://github.com/montricwang/poeticus/issues/180)）。
- 未来确有长期可用性或流量需求，再考虑独立云主机、性能基线、容量及必要的 Retrieval CI/CD。

### 2.2 工程基础补课

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

### 2.3 AI Evaluation

当前已经有 Seed Eval、Retrieval Increment Case、真实 Agent E2E。

下一步更值得补：

- Tool routing regression；
- Retrieval candidate 可见但 Agent 选错的 Case；
- query reformulation 的成功 / 失败样本；
- 多轮上下文与工具调用共同出现时的回归；
- Prompt / 模型更新后的稳定性比较。

单元测试、AI Eval、Trace、生产 E2E 继续分层。

### 2.4 Corpus quality

公开阅读数据仍保留 `imported_unreviewed` 状态。

近期继续：

- 修 EPUB 结构误判；
- 补小序、注释、寓声、缺文等 regression sample；
- 建立 curated correction 与原始抽取之间的明确边界；
- 逐步补充可靠年代 metadata，而不把 Werneror coarse dynasty 回写成阅读库事实。

### 2.5 UX reliability

真实设备问题继续按 Issue 推进：

- iOS 选区；
- 长对话可读性；
- SSE 中断 / 重试体验；
- 目录与阅读区细节；
- 赏析和对话之间的切换。

10 月 14 日的桌面固定双栏、单行目录、自适应分页和提示框统一，已在独立 `feat/frontend-20261014` Worktree 做本地浏览器验证，**尚未合并／上线**。待用户完成视觉验收后，再作为前端 PR 收口并更新现行前端架构说明；不要把开发预览当作线上现状。

### 2.6 诗学画像与推荐（研究阶段）

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

目标先做约 10 本高价值材料的小型 Corpus，建立：

```text
问题类型
→ domain routing
→ curated retrieval
→ source-grounded answer
```

Document Corpus 与实时业务数据继续分开。订单、库存、余额一类实时状态应走 API / DB Tool。

接入新语料或工具前，先查看 [数字人文资源地图](digital-humanities-resources.md)，用 [#184](https://github.com/montricwang/poeticus/issues/184) 验证已有开放数据 / API / 方法是否能替代自行采集、整理或新建系统的工作；未核查权限与增量价值的来源不直接进入生产。

### Search / Web fallback

如果 curated Corpus 证明覆盖不足，再研究开放 Search Tool 的路由和证据权重。

### Multi-span evidence

当前 Retrieval Tool 主要围绕一段文本。全文多线索可继续探索：

```text
多个 span 独立召回
→ Work / source 级证据聚合
→ 必要时二次检索
```

这项工作等真实全文 Case 提供明确增量再开。

## 4. Retrieval 当前停止线

以下内容暂时不进入主线：

- pq512；
- clause BM25；
- reranker / Cross-Encoder；
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

v0.4.0 的当前真实链路应能讲清楚（不再是已销毁的腾讯云 VPS 方案）：

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