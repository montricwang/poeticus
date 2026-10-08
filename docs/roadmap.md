# Poeticus Roadmap

> 更新日期：2026-10-08  
> 当前状态：v0.3.0 发布基线已经形成。公开阅读、Agent、AI Eval、Hybrid Text Retrieval 和独立 Retrieval Serving 均已跑通真实线上链路。

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
- FAISS IVFPQ Serving；
- 独立 Text Retrieval HTTP Service；
- 腾讯云 2C8G CPU production node；
- Railway Agent → HTTPS → Retrieval → candidate → final answer 的真实 E2E。

Retrieval 的阶段性目标已经达到。后续不继续围绕 FAISS 参数、更多 Chunk、更多 sparse ranking 变体做惯性扩张。

## 2. v0.3.0 之后的近期事项

### 2.1 Production hygiene

优先完成已经暴露的运维边界：

- #167：验证 Let’s Encrypt 公网 IP 证书自动续期和 Nginx reload；
- #151：Corpus duplicate / variant self-hit profiling；
- 观察 Railway SFO → 腾讯云上海的长期 latency / timeout；
- 记录真实流量以后，再判断是否需要 4C8G；
- 只有 Retrieval 更新频率开始造成维护负担，再建设完整 CI/CD。

当前 2C8G 没有持续 swap / OOM，扩容不作为预防性动作。

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

v0.3.0 已经可以完整讲一条：

```text
Frontend
→ FastAPI
→ LangGraph Agent
→ Tool routing
→ HTTP Retrieval Service
→ Query Plan
→ Dense + BM25
→ RRF
→ chronology filtering
→ FAISS Serving
→ Linux VPS
→ Nginx / HTTPS
→ production E2E
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