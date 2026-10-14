# 阅读词库无监督聚类实验

> 研究性质的离线可视化；不修改线上数据库、Poem Retrieval 和 Reader。关联 [#157](https://github.com/montricwang/poeticus/issues/157)。

当前使用本地 BERT-CCPoem v1，对 `poeticus-data/reading-corpus/normalized/all_normalized.json` 中 **3,491 首词的原文**编码，得到 512 维向量后用 scikit-learn K-means 聚类。未使用标题、作者、评论、注释或人工标签作为模型输入。

## 打开交互式散点图

在 **WSL 终端**：

```bash
cd ~/projects/poeticus-clustering
bash scripts/experiments/open_cluster_explorer.sh
```

脚本在 Windows 中打开本地 `poeticus-data/reports/recommendations/cluster_full/cluster-explorer.html`。这个 HTML **已经生成，打开时无需启动服务或联网**。也可自行从 Windows 文件管理器打开。

网页支持：

- **t-SNE / PCA**：二维投影切换；缩放、拖动、悬停查看作品；
- **K-means 8 / 16 / 24 类**：聚类数切换。颜色代表无监督产生的组，没有预先指定「豪放」「婉约」等文学类别；
- **按作者着色**：方便检查作者分布是否主导图形；
- **作品搜索与浏览**：搜作者、词牌或正文，点击散点在右侧查看全文、原始向量空间中相似的跨作者作品，以及所属组；
- **分组目录**：按组查看数量、主要作者与中心附近的代表作品，按按钮筛选某一组。

网页里展示的相似度是 BERT 向量余弦，不是文学价值概率。二维点距离受投影算法影响；**K-means 聚类是在 512 维上运行，而不是二维坐标上**。

## 重新计算

在该 worktree 中运行：

```bash
../poeticus/.venv/bin/python scripts/experiments/cluster_reading_corpus.py
```

当前实验复用同一 `~/projects/poeticus/.venv` **作为只读运行环境**；里面已经装有 `numpy`、`scikit-learn`、`transformers`、`torch`、`plotly`。实验不调用云端模型，缓存和结果只写到私有的 `../poeticus-data/reports/recommendations/cluster_full/`，不写回源码仓库。重跑优先复用缓存，缺少的 BERT 分片可以增量补建。语料版本发生变化时需重新生成旧缓存，避免误配。

本脚本基于项目已有的 `scripts/corpus/bert_ccpoem_embedding_build.py:encode_batch`（mean pooling，L2 归一化），而不是另写一套 BERT 编码规则。作品长度均在模型 512 Token 上限以内。K-means 随机种子为 `20261014`，`n_init=10`，聚类数分别为 8、16、24；t-SNE 在 PCA-50 的表示上进行。

## 结果与边界

| K | Cosine silhouette（900 首固定随机样本） |
|---|---:|
| 8 | 0.0910 |
| 16 | 0.0586 |
| 24 | 0.0493 |

这些数值表明**有一定的局部分群结构，但没有可靠的、明显分离的文学流派**。单纯追求高轮廓系数也无法判定哪种聚类最有阅读价值。

本库只有 24 位作者，分布不均：在 K=16 时，有一组 294 首，其中 177 首来自辛弃疾。图形可按作者着色来观察这种偏置。以后如果用于推荐，须再评价作者、词牌、篇幅、题材和内容重复的影响；本轮不做正式推荐上线。

### 验证记录

- BERT 编码向量 `(3491, 512)`；PCA 与 t-SNE 形成 3491 对坐标；各 K 的标签、分组汇总及跨作者近邻均为 3491 条；
- 网页内置 Plotly 的 JS Bundle 及作品数据，离线可打开；
- Windows Edge headless 实际渲染验证：生成散点图层和 16 张聚类目录卡片；交互按钮/搜索的完整人工操作仍由实际浏览器体验验收。


## AutoDL Qwen 全量对照（2026-10-14）

本轮复用原始 3491 首词语料，通过 AutoDL RTX 4090D 生成 Qwen3-Embedding-0.6B 的 1024 维向量。模型使用全文、无 query instruction、L2 归一化的编码设置；GPU 编码实测 6.34 秒（不包含首次下载与准备）。

生成物均存放在 poeticus-data/reports/recommendations/cluster_full/，不提交 Git：

- autodl_transfer/qwen3_all_3491.npy（原始向量）及 _manifest.json（ID 顺序与 SHA-256）。
- qwen_cluster_explorer_data.json、qwen_cluster_metrics.json（本地聚类与报告）。
- qwen-cluster-explorer.html（可单独打开的离线交互图）。

打开 Qwen 图：

    cd ~/projects/poeticus-clustering
    bash scripts/experiments/open_cluster_explorer.sh qwen

不带 qwen 参数则打开原 BERT 图。两张图支持相同的 PCA/t-SNE、K=8/16/24、按作者着色、作品搜索和跨作者近邻。

需要重算 Qwen 聚类时执行（不需要 GPU）：

    ../poeticus/.venv/bin/python scripts/experiments/cluster_reading_corpus.py --model qwen

Qwen 三个 K 值下的高维 cosine silhouette 为 0.0219 / 0.0114 / 0.0066，BERT 为 0.0910 / 0.0586 / 0.0493。K=16 时两个模型的 Adjusted Rand Index 为 0.1457，跨作者前五近邻平均只有 0.28 个重叠。这说明模型几何分群和近邻排序不同，不能推出哪个模型的文学理解能力更强。两模型 cosine 分数的绝对值也不可直接比较。

本轮只做离线调查，暂不接入产品推荐；后续用人工判断的作品相似性小样本检验近邻实用性。
