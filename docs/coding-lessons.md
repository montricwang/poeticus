# 代码问题复盘

这里只收录**已修复且容易重犯**的工程问题，不记录测试输出或每日调试过程。先修复、复测，再决定是否沉淀；同类问题更新旧条目，优先把预防落实到代码检查或回归测试。执行流程见 [开发者指南](development.md)。

## 浏览器测试的离屏副本干扰选择器

- **现象与原因**：首页推荐诗文的离屏测量会临时复制 DOM，宽泛的 `.home-featured-poem header` 同时命中屏幕上的内容与隐藏副本，Playwright 因 strict mode 失败（[#303](https://github.com/montricwang/poeticus/pull/303)）。
- **预防方法**：交互测试定位到真实可见的语义容器（如 `getByRole('region', { name: '推荐作品' })`），不要依赖可能匹配隐藏探针的全局 CSS 选择器。
- **验证方式**：在真实浏览器运行推荐区的桌面/移动 Playwright 用例，确保无重复 locator；只跑 TypeScript 编译不够。

## E2E 测试代码没有纳入 TypeScript 检查

- **现象与原因**：Playwright 误用 `route.request().url`（应为 `url()`），运行时抛 `Invalid URL`；原 `tsc -b` 只检查应用源码，漏掉了 `e2e/` 的类型错误（[#306](https://github.com/montricwang/poeticus/pull/306)）。
- **预防方法**：在 `tsconfig.e2e.json` 中纳入 `e2e/` 并交给既有 `npm run typecheck`，让测试代码和产品代码一样接受编译期检查。
- **验证方式**：`cd frontend && npm run typecheck`；临时恢复 `url` 的错误写法会触发 TS2345，改回 `url()` 后检查通过。

## 测试替身与真实数据库返回类型不一致

- **现象与原因**：真实数据库行是 `DictRow`，测试替身返回 `Mapping[str, object]`；联合类型函数却只声明 `DictRow`，而替身直接把未验证的 `object` 当作列表下标和 UUID（[#306](https://github.com/montricwang/poeticus/pull/306)）。
- **预防方法**：公共只读接口用真实实现与替身共同满足的类型（如 `Mapping`），测试替身在使用外部参数时用 `isinstance` 明确校验，不靠 `Any` / 忽略检查遮盖差异。
- **验证方式**：PR CI 的 BasedPyright 0 errors，并运行 `tests/test_corpus_api.py`；不以 Ruff 通过代替类型检查。

## 页面新增 API 后旧 E2E 夹具失效

- **现象与原因**：首页改为从 `/api/poems/daily` 获取推荐作品后，旧 E2E 只模拟作品目录和详情，还断言已经更改的首页文案，导致测试报错却没有覆盖真实页面行为（[#306](https://github.com/montricwang/poeticus/pull/306)）。
- **预防方法**：接口或页面主路径改变时，同步检查对应 E2E 的请求拦截与断言；需要稳定样本就明确模拟新端点，不用真实日期/数据库决定 UI 测试结果。
- **验证方式**：在无本地后端的 GitHub CI 中运行首页 Playwright，用固定推荐与搜索样本验证首页、进入阅读室及手机/桌面路径。
