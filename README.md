# Poeticus

Poeticus 是一个对话助手，能帮您分析诗歌原文，感受其中诗意。

## 本地测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

自动化测试替换了 Graph 和模型请求，不需要真实 API Key，也不会消耗 DeepSeek Token。

意图分类评测则会调用真实模型，需要先在未提交的 `.env` 中配置 `LLM_API_KEY`：

```bash
python -m evals.evaluate_router --case R011  # 只评测一道题
python -m evals.evaluate_router             # 最近七道题
python -m evals.evaluate_router --all       # 全部十七道题
```

`evals/evaluate_router.py` 只调用分类节点，不执行完整 Graph 的回答分支。需要调试完整执行路径时，启动 `langgraph dev`，在 Studio 中运行细读、查证和澄清三个代表性问题；如已配置 LangSmith Tracing，可以在对应项目中查看每条 Trace。
