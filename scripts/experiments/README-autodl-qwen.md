# AutoDL GPU：Qwen3-Embedding-0.6B 全量编码

> 与 #157 / Draft PR #287 相关。**只负责生成作品向量**，不在远端聚类，不上传到公开仓库。GPU 运行需用户手动启动 AutoDL 实例（按量计费）。

## 1. 先上传（服务器保持关机时即可在本地准备）

已制作的本地小文件位于：

`~/projects/poeticus-data/reports/recommendations/cluster_full/autodl_transfer/`

- `qwen_gpu_input.jsonl`：按 `all_normalized.json` 顺序导出的 3491 首原文和 source_id；约 869 KiB。
- `qwen_gpu_encode.py`：GPU 编码脚本；约 4 KiB。

AutoDL 开机后在实例页面找到 **SSH 登录** 信息，FileZilla 使用 **SFTP** 而非 FTP（按实例页面实际主机名、SSH 端口、账号和验证方式配置，不要把密码提交到仓库）。传到例如 `/root/autodl-tmp/poeticus-qwen/`；请先确认实例数据盘空间够用。

## 2. 在 AutoDL Terminal 运行

```bash
nvidia-smi
python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
python -c 'import sentence_transformers, transformers; print(sentence_transformers.__version__, transformers.__version__)'
```

只有缺少 `sentence_transformers` 或相关包时才安装，尽量沿用镜像现有 CUDA PyTorch：

```bash
python -m pip install 'sentence-transformers>=5.0'
```

切到上传目录运行：

```bash
cd /root/autodl-tmp/poeticus-qwen
python qwen_gpu_encode.py --check-input
python qwen_gpu_encode.py --model Qwen/Qwen3-Embedding-0.6B --batch-size 16
```

第一次运行会从 Hugging Face 下载模型到本机缓存；下载网络不通时可把已缓存的本地 `poeticus-data/models/Qwen3-Embedding-0.6B-*` 目录上传到 AutoDL，改用 `--model /路径/到/本地模型目录`。**遇到下载长时间卡住时先停止计费再排查**，不要无限等待。

只要成功看到 `OUTPUT ...` 和 `MANIFEST ...`，就下载 `qwen3_all_3491.npy`（约 14 MB）及 `qwen3_all_3491_manifest.json` 两个文件；不要上传或下载 1.2 GB 模型权重，除非确实无法从云端拉取。

## 3. 本地核对之后再聚类

把两个结果放回本地：

`~/projects/poeticus-data/reports/recommendations/cluster_full/autodl_transfer/`

运行：

```bash
cd ~/projects/poeticus-clustering
../poeticus/.venv/bin/python scripts/experiments/verify_qwen_gpu_output.py \
  --data-dir ../poeticus-data/reports/recommendations/cluster_full/autodl_transfer \
  --corpus ../poeticus-data/reading-corpus/normalized/all_normalized.json
```

该校验验证：ID 顺序、输入文件/向量 SHA-256、矩阵形状 `(3491, 1024)`、有限值和 L2 归一化。校验通过后才对其做与 BERT 相同的 K-means/PCA/t-SNE 比较。

**GPU 成功生成并下载结果后及时关机**；关机后再做本地聚类/可视化，减少计费。
