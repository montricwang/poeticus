
# Poeticus

**在诗词中阅读，也在诗词中追问。**

Poeticus 是一款面向中国古典诗词的 AI 辅助阅读工具。它将诗词原文、划词提问、典故检索和作品赏析放在同一个界面中，让读者不必频繁离开原文，就能围绕感兴趣的字句展开探索。

项目目前处于 MVP 开发阶段。

## 功能介绍

### 阅读与划词提问

选择一首诗词，在阅读过程中直接选中感兴趣的字词或诗句，向 AI 提问。

例如，阅读苏轼《浣溪沙·新秋》时，可以选中「三星当户」，询问：

> 「三星当户」是什么意思？它与下句的「绸缪」有什么联系？

Poeticus 会结合当前作品、选中的文字和你的问题组织回答，而不只是孤立地解释一个词语。

### 典故检索

遇到典故时，可以要求 AI 查询相关资料，再结合诗词的具体语境解释。

Poeticus 当前接入了 CNKGraph 典故检索服务。AI 可以根据问题决定是否调用检索工具，并在获得资料后继续分析。

检索结果属于候选参考资料，并不意味着相关出处、版本或解释已经经过完整的文献校勘。

### 整首赏析

除了围绕局部字句提问，还可以生成整首作品的阅读辅助内容，包括：

- 现代汉语译文
- 重要词语解释
- 作品整体赏析

### 流式回答

AI 生成回答时，内容会逐步显示，无须等待整篇回答全部生成后才能开始阅读。

## 如何使用

目前可以在本地运行 Poeticus。

### 1. 获取项目

```bash
git clone https://github.com/montricwang/poeticus.git
cd poeticus
```

### 2. 配置后端

安装 Python 依赖：

```bash
python -m pip install -r requirements.txt
```

在项目根目录创建 `.env` 文件，配置模型 API Key：

```dotenv
LLM_API_KEY=你的_API_Key
```

项目默认使用 DeepSeek API。如果需要使用其他兼容的服务地址，可另外设置 `LLM_BASE_URL`。

启动后端：

```bash
uvicorn api:app --reload
```

后端默认运行于 `http://127.0.0.1:8000`。

### 3. 启动前端

打开另一个终端，在项目根目录执行：

```bash
cd frontend
npm install
npm run dev
```

按照终端显示的地址打开页面，通常为 `http://localhost:5173`。

### 4. 开始阅读

1. 从作品列表中选择一首诗词。
2. 阅读原文，选中想进一步了解的字词或诗句。
3. 在对话区输入问题，或直接询问整首作品的内容。
4. 如需整体阅读辅助，可以使用「生成整首赏析」。

## 当前开发状态

Poeticus 仍在持续开发。目前已实现单轮诗词问答、划词交互、典故工具调用、流式回答和整首赏析。

现阶段还有一些限制：

- 对话尚未支持完整的跨轮次上下文。
- 外部资料检索目前主要限于 CNKGraph 典故服务。
- AI 生成的文学解释和文献引用仍可能存在错误，重要结论应进一步核对原始文献。

更多开发计划与已知问题见 [GitHub Issues](https://github.com/montricwang/poeticus/issues)。

## 技术与开发文档

Poeticus 使用 React、TypeScript 和 Vite 构建前端，使用 FastAPI 提供后端服务，并通过 LangGraph 组织 AI Agent 的工具调用与回答过程。

关于 Graph 的具体设计、执行流程和技术限制，请参阅 [LangGraph 架构文档](docs/architecture/langgraph.md)。

运行自动化测试：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
