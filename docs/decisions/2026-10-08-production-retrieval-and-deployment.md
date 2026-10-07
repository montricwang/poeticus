# Production Retrieval / Deployment 决策快照 — 2026-10-08

> 本文件承接 2026-10-07 的 Retrieval Serving 决策。10 月 8 日凌晨已经完成 Linux Benchmark、腾讯云部署、Railway 集成和真实线上 E2E，因此一批昨日仍是 experiment / open 的判断可以升级。

## A. 已有生产证据支撑的决定

| ID | Decision | Level | Origin | Evidence | Status | Re-review trigger |
| --- | --- | --- | --- | --- | --- | --- |
| DEP-001 | Text Retrieval 保持独立服务，Railway Web 通过 HTTP 调用，不把 Qwen / FAISS / BM25 常驻 Web 进程 | 1 | joint | Serving Bundle 约 8.02 GiB；Linux ready RSS 约 4.4 GiB，benchmark 后约 5.3 GiB；真实 Railway → 腾讯云 E2E 已跑通 | active | Retrieval footprint 大幅下降，或未来平台能以更低运维成本承载同等常驻资源 |
| DEP-002 | 第一台生产 Retrieval 节点继续使用腾讯云上海 2C8G、CPU、single worker | 1 | joint | 完整 Corpus 在 2C8G 上启动成功；无持续 swap；5 并发约 1.78 req/s；线上低流量 E2E 可用 | active | 真实流量出现持续 queue / latency，或内存接近 OOM |
| DEP-003 | Retrieval 节点不承载 Poeticus PostgreSQL | 1 | joint | 当前 Web / DB 在 Railway 已稳定运行；Retrieval 是高 RAM / CPU 常驻进程，拆开后故障与资源边界更清楚 | active | Railway DB 成本、网络或可用性形成明确迁移动机 |
| DEP-004 | Retrieval 进程只监听 `127.0.0.1:8787`，公网由 Nginx :443 终止 TLS 并反代；Railway 使用 Bearer token | 1 | AI-proposed / joint | 真实 HTTPS 调用成功；Security Group 未开放 8787；无 token 请求返回 401；Agent E2E 成功 | active | 未来进入私网互联、mTLS、service mesh 或云厂商内网 |
| DEP-005 | 服务部署完成以 localhost `/health` ready 为准，`systemd active` 只表示进程已启动 | 1 | joint | restart 后 systemd 已 active，但模型 / Index 仍加载，Nginx 暂时返回 502；约 18 s 后 8787 LISTEN + health 200 | active | 启动模型改变或引入独立 readiness probe |
| RET-114 | 请求缺少 dynasty 时，由 Retrieval 先看 current-work alias，再看 Werneror exact-author dynasty 分布，得到 corpus-compatible chronology label | 1 | joint | 生产请求显式 `dynasty=null` 时，陆游 Case 重新召回杜甫 rank 6；最终 Agent 正确使用该候选 | active | 公网作品库增加可靠逐首年代；或作者同名 / 多 bucket 导致实际误判 |
| RET-115 | Werneror dynasty 只作为 coarse corpus chronology label，不向用户表达成精确历史断代 | 1 | joint | 部署节点实测：温庭筠、韦庄、冯延巳、李璟、李煜在 Werneror 中全部标为「唐」；其中南唐人物与历史断代明显不一致 | active | Corpus metadata 升级为作者生卒、创作年代或更可靠朝代体系 |

## B. 仍然合理、但需要继续观察

| ID | Decision | Level | Origin | Why now | Status | Re-review trigger |
| --- | --- | --- | --- | --- | --- | --- |
| DEP-101 | 当前公网 Retrieval 继续使用腾讯云上海，而不为了靠近 Railway SFO 立即迁往香港 / 美国 | 2 | joint | 当前真实请求可用；这一阶段优先完成产品闭环，没有测出跨境网络已成为主要瓶颈 | active | 多次 timeout、明显抖动或端到端 latency 显示网络占主要部分 |
| DEP-102 | 需要扩容时先看 CPU / concurrency，再考虑 RAM | 2 | joint | 2C8G 无持续内存压力；5 并发吞吐约 1.78 req/s，CPU 更接近当前资源限制 | active | RSS 上升、swap 持续或 OOM；或 profiling 显示 CPU 并非主要瓶颈 |
| DEP-103 | 暂时保留手动代码同步 + systemd restart，不在 v0.3.0 前继续做完整 CI/CD | 2 | joint | 生产闭环刚完成；服务器无法稳定访问 raw.githubusercontent.com，先用本地开发机上传更稳 | temporary | Retrieval 改动频率增加，手工部署开始导致版本漂移或操作错误 |

## C. Working defaults

| ID | Working default | Level | Origin | Why now | Re-review trigger |
| --- | --- | --- | --- | --- | --- |
| DEP-201 | Retrieval systemd unit 使用单进程 / 1 worker | 3 | AI-proposed | 避免多 worker 复制 Qwen + FAISS 常驻内存；当前流量足够 | 并发成为真实瓶颈后测进程模型 |
| DEP-202 | Railway → Retrieval HTTP timeout 15 s | 3 | AI-proposed | 远高于当前常见 query latency，给跨境抖动留余量 | 有真实 latency distribution / SLO 后 |
| DEP-203 | 第一版公开 endpoint 使用 IP HTTPS，而未绑定独立域名 | 3 | joint | 能快速完成 TLS + Agent E2E；当前没有域名需求 | 证书运维、IP 变更、可读性或 CDN / DNS 需求出现 |
| DEP-204 | 更新代码后 readiness 最长等待约 120 s | 3 | AI-proposed | 实测 cold start 约 18–35 s；120 s 给异常机器留诊断余量 | 启动模型明显变化 |

## D. 已解决的 2026-10-07 Open Questions

| 原 ID | 结论 |
| --- | --- |
| RET-301 | **Resolved**：8 GiB 足够当前 single-worker full Corpus Serving；无持续 swap / OOM |
| RET-302 | **Partially resolved**：2C8G 5 并发约 1.78 req/s，足够早期低流量；生产并发上限仍需真实流量决定 |
| RET-303 | **Partially resolved**：CPU Serving 可用；不同 Query 仍有明显延迟差异，当前没有必要继续专项优化 |
| RET-304 | 保持 open：全文 multi-span 仍是未来能力，不影响 v0.3.0 |
| RET-305 / 306 | 保持 open：curated 评论 RAG / Web Search 等留到下一阶段 |
| RET-307 | 保持 open：Corpus duplicate / variant self-hit 继续由 #151 跟踪 |

## E. 新的 Open Questions

| ID | Open question | Level | Origin | 当前已知 | 下一验证 |
| --- | --- | --- | --- | --- | --- |
| DEP-301 | Let’s Encrypt 公网 IP 证书能否稳定自动续期并让 Nginx 使用新证书 | 4 | joint | Certbot 已报告 scheduled renewal；尚未走过第一次真实续期 | #167 |
| DEP-302 | 是否需要为 Retrieval 建立自动部署 / artifact 发布流程 | 4 | joint | 当前手工 SCP 可用；服务器访问 GitHub raw 曾长时间卡住 | 等下一次 Retrieval 代码更新观察维护成本 |
| DEP-303 | Railway SFO → 腾讯云上海的网络稳定性是否会成为生产瓶颈 | 4 | joint | 当前 E2E 成功；尚无长期 latency / failure 数据 | 收集真实请求与 timeout，再决定香港 / 海外节点 |
| DEP-304 | 是否升级 4C8G | 4 | joint | 当前 RAM 足够，CPU / 并发更紧；低流量尚未形成升级需求 | 真实 p95 / queue / throughput 达到产品痛点 |

## 这次被真实故障纠正的判断

### “规格越宽裕越稳”不足以决定第一台机器

从 16 GiB / 8 vCPU 候选一路收敛到 2C8G，最后 2C8G 实测通过。以后容量选择优先从测量数据和最小可行规格开始。

### “进程 active”不能代表服务 ready

systemd 先启动 Python 进程，Qwen 与 FAISS 仍要继续加载。Nginx 在这段窗口会拿到 connection failure 并返回 502。部署脚本必须等待 health ready。

### “当前公开词集可以统一标宋”会制造数据语义错误

实际阅读库包含晚唐 / 五代词人；随后又发现 Werneror 自己把南唐人物标为唐。Chronology inference 最后留在 Retrieval Corpus 内部，并明确叫 corpus-compatible label。

## References

- #145 / #146 — Retrieval Serving 与本地 benchmark
- #159 — metadata v2
- #160 / #161 / #162 — Linux Deployment Spike 与服务器规格
- #164 / #165 — 线上 dynasty context 修复与最终 E2E
- #166 — 服务器 / 存储 / 服务通信补课
- #167 — TLS certificate renewal 运维验证
- #151 — duplicate / variant self-hit
- #163 — 唐宋 Serving Profile（deferred）
