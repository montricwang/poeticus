# Poeticus｜教学与 AI 协作手册

这份手册记录 Poeticus 开发过程中已经形成的合作方式。目标是让项目继续前进，同时让用户逐渐建立稳定的工程心智模型，避免两种极端：每一步都停下来上课，或连续执行很多天以后只剩下“代码能跑”。

## 1. 基本分工

长期原则：

> **原理必须理解，判断必须参与，执行可以委托。**

对应到实际开发：

- **原理**：用户需要知道关键组件在系统里的位置、输入输出、资源影响和主要失败方式；
- **判断**：服务器规格、架构边界、是否增加复杂度、是否接受技术债，需要把证据和替代方案摆出来；
- **执行**：命令、批量改文件、测试、PR、部署等机械步骤可以大量交给 AI。

不要求用户记住每条 shell 命令，也不要求逐行审阅所有实现。需要保住的是以后能重新推导“为什么这么做”。

## 2. 教学节奏

### 先建立一层，再打开下一层

讨论一个组件时，先把当前抽象层站稳。

例如谈 Retrieval Service：

```text
Agent
→ HTTP
→ Retrieval Service
→ candidates
```

这一轮先理解服务边界。等边界清楚后，再下钻：

```text
Retrieval Service
→ Qwen encoder
→ FAISS / BM25
→ metadata
```

如果同一轮同时展开 TCP、TLS、进程、内存映射、PQ、Linux page cache，认知负担会急剧上升。

### 用真实失败决定什么时候补课

工程执行中出现一次小错误，不需要立刻展开成完整课程。

当同一类问题反复出现，或者它已经影响判断，就单独开一个教学 Issue。今天的服务器部署就是这种情况：

- 服务器规格怎么选；
- disk / RAM / CPU 分别受什么影响；
- cold / warm 为什么不同；
- systemd active 与 service ready 有什么差别；
- Nginx、端口、安全组、HTTPS 怎样串起来。

这些问题已经集中进入 #166，后续用 Poeticus 的真实数据上一堂短课。

## 3. 解释技术概念的写法

重要概念先给一句可以长期记住的核心句，再补正式术语和边界。

例如：

> **RSS 大致回答：这个进程现在实际占着多少内存。**

然后再讨论：

- shared pages；
- allocator；
- page cache；
- peak RSS；
- 多 worker 是否复制内存。

普通关系尽量用普通中文描述“谁做什么、为什么、结果怎样”。成熟术语正常使用，不再额外发明抽象名词。

## 4. 执行过程中 AI 需要主动暴露的判断

AI 连续推进工程时，要特别记录这些内容：

- 新增架构边界；
- 服务器 / 数据库 / 索引选型；
- cache、timeout、worker、Top-K 等默认值；
- 因 benchmark 改变的原判断；
- 当前明确不做的优化；
- 已知但暂时接受的技术债。

这些内容先进入临时 decision ledger。阶段结束时再分流：

```text
当天发生了什么
→ devlog

系统现在是什么
→ architecture / deployment docs

长期架构选择
→ ADR

为什么这样选、证据多强、何时重审
→ Decision Register

还没做完的事情
→ Issue

用户可见的阶段成果
→ Release notes
```

## 5. 遇到线上故障时先定位层级

今天的 502 给出了一套以后继续复用的排查顺序：

```text
process
→ port
→ local health
→ reverse proxy
→ public endpoint
→ caller
→ product behavior
```

具体问题依次问：

1. 进程存在吗？
2. 端口真的监听了吗？
3. localhost 请求成功吗？
4. Nginx 能连到 upstream 吗？
5. HTTPS 公网入口正常吗？
6. Railway 能调用吗？
7. Agent 拿到结果后用对了吗？

先找到失败层，再修改那一层。

## 6. 资源选型先看测量

服务器选型不从“听起来够不够”开始。

当前 Poeticus 的例子：

```text
本机 steady RSS ≈ 5.27 GiB
Serving Artifact ≈ 8.02 GiB
        ↓
先测 2C8G Linux
        ↓
RAM 足够，无持续 swap
5 并发约 1.78 req/s
        ↓
当前更值得关注 CPU / concurrency
```

以后也沿用这个顺序：

1. 测本地资源；
2. 选一个最小可行候选；
3. 在目标 OS 重测；
4. 看瓶颈属于 CPU、RAM、disk 还是 network；
5. 只扩真正紧张的资源。

## 7. 用户反馈可以推翻 AI 的默认路线

今天有三个典型例子：

### 服务器地域

AI 最初偏向 DigitalOcean SFO。用户指出国内云同样适合第一轮资源验证，路线随即改成腾讯云上海。

### 服务器规格

短暂考虑 8C16G 后，用户继续追问“为什么要这么大”，最终回到 2C8G 最小可行 Spike。

### 朝代上下文

AI 一度提出把当前阅读库统一标成“宋”。用户指出温庭筠、韦庄、李煜等实际存在于库中，这个方案立即撤回。最后改成 Retrieval 使用 Werneror metadata 做 corpus-compatible chronology inference。

因此 AI 提出的工程默认值始终保持可撤销。用户发现前提不对时，优先修正前提。

## 8. 密集开发之后安排消化点

连续几天做项目时，大量判断发生在局部：

- 改一个 Query；
- 看一个 Benchmark；
- 调一条部署命令；
- 修一个 502；
- 换一个过滤条件。

这些局部判断本身很消耗注意力，也容易让整体模型散掉。

每完成一个明显阶段，应安排一次“停止执行、整理模型”的时间：

- 画当前架构；
- 解释关键资源；
- 复盘三个最重要的失败；
- 把仍然模糊的概念变成教学 Issue；
- 确认下一阶段不继续沿着惯性扩张。

v0.3.0 之后，Retrieval 已经适合进入这种消化阶段。

## 9. 命令与自动化

重复操作应逐渐收敛成脚本。

今天手工经历了：

```text
git pull
→ scp
→ py_compile
→ copy
→ systemctl restart
→ sleep
→ health
```

随后发现固定 sleep 会误判 readiness，因此未来脚本应循环检查 localhost `/health`。

脚本的目标是减少机械负担。用户仍需要知道每一步在系统里改变了什么，但无需反复手敲同一组命令。

## 10. 当前待补的基础课

#166 已记录下一堂工程基础课：

**从 Poeticus Retrieval 部署理解服务器、存储与服务通信。**

重点用今天的真实数据讲：

- database / artifact / index；
- CPU / RAM / disk；
- FAISS 大小与资源影响；
- cold / warm；
- process / port / health；
- localhost / public endpoint；
- reverse proxy / HTTPS / token；
- service-to-service communication；
- 容量升级判断。

完成后，再回头看今天晚上的部署记录，应该可以从“很多细碎错误”恢复成一张完整的系统图。
