# 《唐宋词鉴赏辞典》离线论证动作提炼

目标：利用本地 Qwen3.5-4B，把已整理的 1505 篇研究记录进一步拆解为「材料 → 可重复的操作 → 推论 → 证据边界」。该步骤不采用原有十四类方法标签，后续再对这些具体动作聚类，并选择原文回读验证。

## 一、启动 Windows 本地 GPU 模型

在 Windows PowerShell 中执行（启动脚本已复制到 D 盘，避免 PowerShell 访问 WSL UNC 路径失败）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Poeticus\poeticus-data\tools\local-llm\start_local_critic_model.ps1"
```

脚本启动已安装的 Windows Vulkan `llama-server.exe`，加载已复制到 `D:\Poeticus\poeticus-data\tools\local-llm\models\` 的 Qwen3.5-4B GGUF，监听 **127.0.0.1:8091**。保持此终端打开。当前机器 WSL2 已配置 `networkingMode=mirrored`，WSL 可以使用同一环回地址连接该服务。WSL 里的原模型仍然保留，复制是因为 Windows 无法直接读取原来的 WSL 模型路径。

服务器日志需显示 Vulkan/GPU 层卸载成功，才算启用了显卡。否则不要以 GPU 速度估算任务。

## 二、在 WSL 启动批处理

```bash
cd ~/projects/poeticus-intertext-pilot
python3 scripts/research/offline_critic_actions.py --limit 3
```

先检查三篇输出的逻辑、引文和耗时，再继续：

```bash
python3 scripts/research/offline_critic_actions.py --all
```

同样的命令支持断点续跑；可随时按 Ctrl+C 停止，已保存的篇目不会覆盖。想看进度：

```bash
python3 scripts/research/offline_critic_actions.py --status
```

输出只写入私有数据目录：

`~/projects/poeticus-data/critic-methods/results/offline_actions_cards_v1/`

- `records/0001.json`：每篇动作与经过原记录短引核对的证据。
- `errors/0001.json`：重试之后仍失败的文章；修复服务或调整设置后重新运行即可。
- `run-config.json`：模型、输入哈希与提示词版本，防止断点续跑时不小心混合不同实验。

脚本逐篇显示当前编号、每篇耗时、平均耗时与预估剩余时间。它只允许访问本地或私有网络上的 HTTP 模型服务，不调用云 API。

## 三、之后才做原文回读

先在动作聚类后选出有代表性、有争议或低置信度的篇目，再运行：

```bash
~/projects/poeticus/.venv/bin/python scripts/research/offline_critic_actions.py --mode original --numbers 1,20,120
```

这次读取真实 EPUB 原文，而不是昨天的提炼记录。原文结果另存于 `offline_actions_original_v1`，不会污染第一轮成果。

需要对照实验时，也保留 `--mode original --all`。它会显著增加推理时间，不建议作为默认步骤。

## 判断成果是否值得进入下一阶段

抽查最初 3—10 篇：操作是否具体、是否与证据匹配、能否据此重现评论者的推理，而不是套用“细读”“比较”等空泛名称。若本地 4B 模型错误率过高，保留已产出结果，先调整提示词或模型，再用**新的输出目录**重跑，不要把两套实验混在一起。
