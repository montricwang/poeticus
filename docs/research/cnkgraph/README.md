# CNKGraph 公开 API 普查（2026-10-20）

关联 [#346](https://github.com/montricwang/poeticus/issues/346)。这是**首轮只读冒烟结果**，尚不是接口业务正确性、授权、可用于商业服务的验收结论。

## 阅读报告

打开 [深色交互式 HTML 报告](cnkgraph_audit_report.html)。HTML 内嵌完整元数据，可离线使用，提供路径/领域/状态筛选、响应结构展开和人工复核。复核标记仅保存在浏览器本地，也可以主动导出 JSON；源 JSON 不受影响。

本轮素材：

- `api_inventory.json`：71 条 Postman 示例、105 个 Swagger HTTP 操作（103 条路径）的声明、请求和返回 Schema 摘要；保留 12 个原始 Postman 领域。
- `probe_batch_0.json` 至 `probe_batch_3.json`：全部 71 条 Postman 示例的测试记录，重复输入变体保留。
- `probe_batch_4.json`：85 条按方法+原始路径字面比对未被 Postman 覆盖的 Swagger 记录；其中存在同一实际端点的 URI 参数/大小写变体，**85 不是确认新增 85 个互异 API**。
- `cnkgraph_audit_report.html`：以上数据的自包含浏览器视图。

每条记录展示 HTTP 状态、单次耗时、最多 100 KiB 的响应采样规模、JSON 形状、缺少测试样例/主动跳过原因。**不保存完整版权正文、调用凭据**；HTML 不会重放外部请求。

## 更新数据 / 重新生成

项目根目录：

```bash
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --inventory
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 0
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 1
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 2
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 3
.venv/bin/python -m scripts.experiments.cnkgraph_api_audit --probe --batch 4
.venv/bin/python -m scripts.experiments.render_cnkgraph_audit
.venv/bin/python -m pytest -q tests/test_cnkgraph_audit_report.py
```

探测脚本有 0.5 秒串行间隔、只读方法白名单、响应截断与导出/协议/会话端点保护。**不要把复现命令当作每次开发的默认测试**：重新请求远端有服务负担，也会覆盖原始结果；仅在需要验证新版本时单独运行，并保留新的日期证据。

## 验收边界与下一步

- JSON 解析成功（`valid_shape`）只证明 HTTP 和响应形状。真正业务可用还须用已知合法 ID/文本确认返回含义、原文出处、实体标识与语义。
- HTTP 400、404 也可能由旧示例 ID、路径参数替换引起；204、302、非 JSON 和超时须单独辨认。截断样本不代表整个响应可解析。
- 新 Swagger 具有 `/api/Tool/Label`、`LabelAndResolveEntity` 和 `AnalyzeCi`，与历史失败的 `/api/tool/labelize` 是不同路径。不能将新接口的存在等同于旧接口已恢复，或格律校验业务正确。
- 官方 [开放资源与使用说明](https://cnkgraph.com/Home/OpenResources) 标明研究学习限非商业。任何生产接入、长期缓存、批量入库、对外公开服务都需另行明确权限。当前仅用于本地低频科研实验。

等人工逐项复核并取得使用许可后，再选需要接入或保存的接口；不按 API 数量扩张 Agent Tool。
