# Reader 100｜全工具合并后首轮 20 题冒烟测试

日期：2026-10-20。分支：`eval/agent-reader-full-tools-20261020`（从 `main@6db35a0` 建立）。

## 基础版本与范围

- 已合并：CNKGraph 首批研究工具 PR #356（`2f5bb53`）、DeepSeek Search/Fetch PR #365（`cb2d3aa`）、综合评测脚本 PR #358（`de3e930`）、萌典/Wikisource PR #369（`6db35a0`）。
- 本轮是 **20 题预检／冒烟**，不是完整 100 题的增量评估：分别选 `reader_001–007`（基础 7）、`reader_041–047`（进阶 7）、`reader_076–081`（研究 6），与旧版相同题号比较。
- 模型 `deepseek-flash`；每题至多 2 次工具调用；由 Agent 自主选择，不硬编码工具 Policy，不强制检索。
- 在**本地私人非商业环境**中，使用已有 `POETICUS_RETRIEVAL_URL` + `POETICUS_RETRIEVAL_TOKEN`、Document RAG、CNKGraph、DeepSeek Web、萌典/Wikisource 开关。零题 `--require-tools` 预检确认本轮真正注册 **14 项工具**。
- 本地完整输出及逐题 Trace 保存在被 Git 忽略的 `data/reports/reader_100_full_tools_20261020.json`。**不得把私人密钥、评论语料全文、第三方网页全文或缓存结果提交到公开仓库**。

## 数字结果

| 题组 | 题数 | 此轮主动用工具 | 旧版同题用工具 | 此轮调用数 | 平均耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基础 001–007 | 7 | 2 | 0 | 2 | 2.63s |
| 进阶 041–047 | 7 | 6 | 5 | 7 | 8.18s |
| 研究 076–081 | 6 | 2 | 1 | 4 | 7.11s |
| **合计** | **20** | **10** | **6** | **13** | — |

20/20 获得非空回答；13 次工具调用**没有执行异常**，其中 CNKGraph 古籍检索 1 次是正常的 `no_hit` 而非失败。平均耗时仅是当前机器与外部 API 环境下的本轮观测，不应外推到全站。

调用构成：`search_documents` ×8、`lookup_moedict` ×2、`search_wikisource` ×1、`search_classical_books` ×1、`web_search` ×1。其余开放工具本轮未调用，**不能据此断言它们无用**。

具体可追踪例子：
- `reader_003`、`004`：以前不调用工具；现在 Agent 主动查萌典，工具均返回 `ok`。
- `reader_047`：由旧版直接回答变成词话 RAG + 官方维基文库搜索，两次都返回 `ok`。
- `reader_076`：本轮词话 RAG + CNKGraph 古籍查找，后者 `no_hit`；不能视为有古籍出处支持。
- `reader_077`：旧版连续两次古籍 404；本轮选择 RAG + DeepSeek Search，均返回 `ok`，但搜索成功不等于完成底本校勘。
- `reader_078–081`：仍由模型直接作答。是否应检索须对照 Gold 逐项审查。

## 判断与下一步

1. **基础连通性通过**：十四项 Tool Schema 实际注册，选中的萌典、Document RAG、Wikisource、CNKGraph 与 DeepSeek Web 均可发起真实调用；本样本未见未注册 Tool、认证失败、HTTP 404 被误当成功等执行异常。
2. **增量质量未证明**：本样本刻意挑选了中级评论题密集段，既非随机也非盲测，不可把 6→10 的工具使用增长误作准确率提升。尚未逐题核实回答、文献引文、版本、错韵解释和来源真实性。
3. **下一步**：沿同样模型、工具开关、预算、数据集 SHA 和输出文件断点完成剩余 80 题；人工定向抽查「找到证据却没引用／网页摘要充当原文／研究题绕过工具／冲突版本」等案例；再选择少数题做开关对照，检查工具收益、费用、延迟与错误。
4. CNKGraph 的公开 API 仅供非商业研究，未获公开部署授权；默认禁止在公开 Poeticus 后端开启相关开关。DeepSeek Search/Fetch 为计费服务；Wikisource 与萌典仍可能有网络超时。

运行入口：`python -m scripts.evals.run_agent_reader_100 --help`；本轮预检／操作说明见 [Eval README](README.md)。关联 Issue #357、#355、#364，PR #356、#365、#358、#369。
