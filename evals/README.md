# Poeticus AI Eval

> Seed Eval 最初基线：v0.3.0（2026-10-08），Reader 100 首轮真实运行于 2026-10-20。本目录同时包含 Seed Eval、Retrieval Increment Eval 的小规模可重复 Case；完整线上 E2E 验收记录另见 [v0.3.0 Release](../docs/releases/v0.3.0.md) 与 [开发日志](../docs/devlog/2026-10-08.md)。

Eval 用来回答**哪一类问题改善了、改善是否真的来自工具证据、哪里仍会失败**。当前不搭通用评测平台，不将小样本 Case 得分包装成全站准确率，也不默认引入 LLM-as-a-Judge / RAGAS。

## 当前评测层次

| 层次 | 对象 | 主要判断 |
| --- | --- | --- |
| 单元 / Contract 测试 | Query Plan、RRF、Eligibility、Retrieval Client/Server、HTTP 契约等 | 确定性行为与接口是否回归（见 `tests/`） |
| Seed AI Eval | `seed_cases.json`、`scripts.evals.run_seed` | 当前 Agent 使用 Tool / Evidence 的选择和回答表现 |
| Retrieval Increment Eval | `retrieval_increment_cases.json`、`scripts.evals.run_retrieval_increment` | 独立 LLM 与一次 Retrieval Tool 增强的增量、目标候选是否确实由工具提供 |
| 真实 Agent / 生产 E2E | Tool routing、必要时二次 Query、Railway → Retrieval → 最终回答 | 真实服务链能否工作；与离线 Eval 不相互替代 |
| **Reader 100 综合候选题** | `agent_reader_100_cases.json` + [100 题审阅表](agent_reader_100_review.md) | 首轮 100 题真实模型执行完成；工具选用/回答质量待人工 Gold 校勘和增量对照 |

注意两种对照**不是同一个控制组**：Seed 的 `control_no_tools` 仍使用当前 Agent Prompt / Tool Schema、只禁用执行；Retrieval Increment 的 `standalone_llm` 则不注入 Poeticus Agent Prompt 或 Tool Schema，才能观察更接近模型自身参数知识的表现。

## Reader 100：综合读者题库（2026-10-20 草案）

新题库独立于 [#344 Document RAG 专项 100 题](https://github.com/montricwang/poeticus/issues/344)；它讨论的是文学阅读与研究型 Agent 的**综合对话能力**，不是只检查 Document Hybrid 召回率。

- 源数据：[agent_reader_100_cases.json](agent_reader_100_cases.json)，**100 题**（基础 40 / 进阶 35 / 研究 25），涉及 17 类问题域，部分与已有 Seed Eval 的作品上下文复用，另有独立研究问答。
- 人工快速审阅：[agent_reader_100_review.md](agent_reader_100_review.md)，按读者层级列出完整 100 题。生成命令：`python -m scripts.evals.render_agent_reader_questions`，避免维护第二份人工拷贝。
- JSON 每题只包含 `question`、可选 `fixture_id`／`selection`、`level`、`topic`、`review_focus`、分组与待核验标记；**不提供预设 Tool Policy、标准答案、检索答案片段**。
- `fixtures` 保留公共领域古典词作的**候选原文**，包含来源为旧 Seed 的关联与新增片段，均标记待独立核查准确版本；`text_scope=excerpt` 代表节选，不能假装给词律工具提供了完整作品。
- 80 题标记为开发整理，20 题标记为预留人工复查。**预留不等于正式 held-out**；只有经人工审核、固定源版本和实验隔离后才可称为验证集。
- 部分题可能需要尚未接入的类书、词人行迹、年历及更强古籍查证能力，这是**发现覆盖缺口**，不要求为每个问题写固定路线。
- 2026-10-20 已通过 `scripts/evals/run_agent_reader_100.py` 完成首轮 100 题真实回答（当时仅有 8 项工具注册）：19 题调用工具，32 次调用中 23 次成功、9 次失败。这里的 `100/100` 表示非空回答，**不是正确率**；仍未建立全部题的 Gold 和独立文学质量评分。下一轮需同时检验工具实际命中与回答证据，不根据 Topic 标签强制调用。

检查：`python -m pytest -q tests/evals/test_agent_reader_100_cases.py`。进度见 [#357](https://github.com/montricwang/poeticus/issues/357)，CNKGraph 实验关联 [#355](https://github.com/montricwang/poeticus/issues/355)。

### Reader 100：全工具回归预检与执行

**先合并工具相关 PR，再从最新 main 开独立测试分支。** 现在 Agent 具备 14 项候选工具：原有典故/出处/诗文检索/Document RAG 4 项、CNKGraph 5 项、DeepSeek Search/Fetch 2 项、萌典/Wikisource 3 项；但**只有启动进程实际注册的**才可用。

每轮记录真实工具清单，避免重演首轮「诗文 Retrieval 服务已运行，但 Agent 缺少 `POETICUS_RETRIEVAL_URL` / `POETICUS_RETRIEVAL_TOKEN`」的环境缺口。单独的 `/health` HTTP 200 不能证明认证请求成功。评测在进程启动前读取**主工作树私有 .env**，不向测试 worktree 复制或提交 Token；先对检索接口做一次有 Bearer 的真实查询，确认返回结构符合客户端契约。CNKGraph 只限隔离本地非商业实验；Web 搜索是计费服务，公众环境仍默认关闭。

在 WSL 下，先做只检查工具的零题预检（不会发起模型问题、不会重算首轮 100 题）；以下两项新来源开关**只在当前命令进程启用**：

```bash
POETICUS_DEEPSEEK_WEB_TOOLS_ENABLED=true \
POETICUS_CLASSIC_REFERENCE_TOOLS_ENABLED=true \
python -m scripts.evals.run_agent_reader_100 \
  --env-file /home/montric/projects/poeticus/.env \
  --enable-cnkgraph --count 0 \
  --output data/reports/reader_100_all_tools_run.json \
  --require-tools lookup_allusion lookup_reference search_predecessor_texts search_documents \
    analyze_ci_meter lookup_ci_tune lookup_rhyme resolve_entities search_classical_books \
    web_search web_fetch lookup_moedict search_wikisource read_wikisource_page
```

**预检失败就不要开始收费评测。** 应检查 .env 路径、token 与真实服务、全部开关、当前 Git 分支；Runner 会报出缺失工具，不会默默以旧 schema 记录 14 个工具。通过后用同样命令更换 `--count 20` 试跑基础/进阶/研究分层题（必要时指定 `--offset`），核查 URL 证据、超时/404、无命中与未检索自述，然后使用相同输出文件 `--count 100` 断点续跑。不同开关或模型不可复用已有输出：Runner 会拒绝不一致的配置。不要把「调用次数更多」当成质量提升。

Trace 现在保留有界的 CNKGraph 书卷与格律判定信息，以及 DeepSeek/Wikisource/MoeDict 的 URL、pageid/revision 与短片段；**不保存第三方整页正文，不将摘要冒充已核原典。** 成绩需要人工抽查和针对性的工具开关对照，不由已回答题数直接计算。


## Dataset

`seed_cases.json` 中每条 Case 只记录：

- 用户输入；
- Tool 是否应当使用；
- 回答至少应覆盖什么；
- 不能无依据声称什么；
- 这道题为什么值得保留。

Case 描述问题本身；某次模型输出属于 Run，不写回 Case。

第一批数据仍是 `draft`。后续发现真实失败时直接补新的 Case；旧 Case 如果本身有问题，标记 deprecated，不静默删除。

## 运行

需要本地已有 `LLM_API_KEY` 等 Poeticus 配置。

只跑一题：

```powershell
python -m scripts.evals.run_seed --case allusion_fenglangjuxu
```

跑全部题并保存结果：

```powershell
python -m scripts.evals.run_seed --output evals/results/seed_run.json
```

每题会比较：

- `control_no_tools`：与当前 Agent 使用同一模型、Prompt 和 Tool Schema，但强制 `tool_choice=none`；
- `current_agent`：走当前 LangGraph Agent，允许它按现有规则调用 Tool。

这不是对所有改动做严格学术消融，只是当前阶段最便宜、最容易解释的一组对照。

## Retrieval Increment Eval

固定案例在 [`retrieval_increment_cases.json`](retrieval_increment_cases.json)。当前对比：

- `standalone_llm`：不经过 Poeticus Agent Prompt，不提供工具；
- `tool_augmented_llm`：同类输入，允许一次本地 Text Retrieval 工具调用；
- Retrieval 结果本身另记录召回、排序和目标是否可见，不能仅凭最终答案正确就宣称 RAG 有增量。

关键字段包括 `target_supported_by_tool` 与 `target_rank_in_tool_candidates`：如果模型答对了，但工具根本没有返回目标文本，不能把这一成功计为 Retrieval 的贡献。经典互文经常属于模型原本就知道的知识；长尾案例（如陆游 → 杜甫）更能检验真实增量。

本地拥有 Werneror Work、FAISS / BM25 / Qwen 等 Artifact 及模型 API 配置后，运行：

```bash
python -m scripts.evals.run_retrieval_increment --output-prefix evals/results/retrieval_increment_run
```

该脚本需要本地大型构建产物，不属于无密钥、无 Corpus 的普通 CI；精确逻辑回归另由 `tests/evals/test_run_retrieval_increment.py` 等测试覆盖。完整 Agent 连续 Tool Calling、线上 Nginx / TLS 与生产服务联通仍需独立 E2E，不能由单次 Tool Eval 替代。

## 从私人编者注中挑选候选 Case

当前私人 normalized JSON 仍保留 `content.annotations` 与 `content.commentaries`。先做整体画像，不把几千条文本直接塞进评测集：

```powershell
python -m scripts.evals.profile_editorial_notes
```

默认读取：

```text
data/output/all_normalized.json
```

并在本地生成：

```text
data/reports/eval_editorial_profile.json
data/reports/eval_editorial_profile.md
```

报告分别统计 annotations / commentaries 的覆盖率、每首数量、长度分布、重复项、常见文本特征和词集分布。词集表会同时给出作品数、覆盖率和每首平均元素数，避免把“收录作品多”误当成“注释更密”。

对 annotations 还会额外做一层轻量结构筛选：`headword_colon`、`quoted_source`、`cross_reference`、`long_source_note`、`other`。这只是按文本形态帮助挑候选 Case，不把它包装成可靠的“词义 / 典故 / 化用”语义分类。对冒号前的短词头，还会检查它能否在本词正文直接找到。

这些报告包含商业出版物的少量截断派生文本，只用于本地分析，不能提交到公开仓库。

## 从画像进入候选抽样

完成 annotation 画像后，不继续扩大分类规则，直接从两个相对干净的结构池中抽候选：

```powershell
python -m scripts.evals.build_eval_candidates_10061450
```

默认生成：

```text
data/reports/eval_candidates_10061450.json
data/reports/eval_candidates_10061450.md
```

当前只抽两类，各 30 条：

- `headword_colon`：短词头 + 冒号，且词头能在本词正文直接找到；
- `quoted_source`：编者注末尾带明确作品来源的前人引文。

抽样会在不同词集之间轮转，避免辛弃疾、黄庭坚等大词集淹没候选池。结果只作为人工挑选 Eval Case 的候选，不自动把 `quoted_source` 判定为“化用”，也不自动把 `headword_colon` 判定为“词义解释”。

这类诊断 / 抽样脚本以后默认在文件名后附 `MMDDHHMM` 八位时间戳，避免不同轮次脚本和报告互相覆盖。

### 扩大关系候选样本（10061542）

在 30 条 `quoted_source` 试标之后，下一轮扩大到 100 条关系候选，同时保留 50 条词头候选：

```powershell
python -m scripts.evals.build_eval_candidates_10061542
```

默认生成：

```text
data/reports/eval_candidates_10061542.json
data/reports/eval_candidates_10061542.md
```

这一轮仍然只做抽样，不自动给 `quoted_source` 关系分类。先人工标约 100 条，观察 taxonomy 是否稳定，再决定是否引入 AI 辅助初标。

## Reader 100：首轮真实 Agent 运行（2026-10-20）

本题库的首次运行使用了 PR #358 的 100 道候选题与 PR #356 的本地未合并 Agent，逐题调用真实 deepseek-flash。完整答案和工具调用记录保存在 Git 忽略的本地 data/reports/agent_reader_100_first_pass.json；**请勿提交包含私人文献检索结果的运行文件**。

- 100 道题均返回非空答案；这只是完成率，不是正确率。
- 本次实测向模型注册了 8 个工具：典故、出处、Document RAG 和 5 个 CNKGraph 研究工具。Text Retrieval 服务未配置，第 9 个工具未注册；单题真实工具调用预算仍为 2 次。
- 19 题发生工具调用，总计 32 次；23 次成功，9 次失败（5 次尝试调用未配置的 Text Retrieval，4 次古籍检索 HTTP 404）。CNKGraph 新工具中词律、词牌、古籍有调用，韵典、实体识别为 0 次。
- 尚未做人工 Gold、引用真实性复核、A/B 对照；输出是可审计的第一轮过程证据，不代表性能提升。

断点续跑脚本：scripts/evals/run_agent_reader_100.py。它会按 Case ID 跳过已完成的题目，记录工具明细与每题延迟；不会自动判断文学回答正确性。应先确认运行的后端代码包含 CNKGraph 研究工具，并仅在**个人本地非商业环境**开启；私有模型配置可通过 --env-file 指定。用 --offset 和 --count 分批执行，变更题集或工具配置时使用新的输出文件。

本轮结果后续复核、任务与失败案例见 Issue #357；相关 API 功能实现见 PR #356。


2026-10-20 证据追踪增强：`scripts/evals/run_seed.py` 现在对 CNKGraph 非 Evidence 格式的工具结果保留受限的书名/BookId/VolumeId/短命中片段，以及钦谱/龙谱具体韵字、错韵和词体的摘要。这样可以事后区分**工具实际报告**与模型推论；不保存第三方整卷全文、完整 HTML 或冗长实体属性。修复前的首轮日志不能自动补出当时被丢弃的证据字段；新的 Trace 格式需要重新运行题目才能产生。
