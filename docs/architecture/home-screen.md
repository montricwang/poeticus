# 首页：每日推荐的布局与预览规则

本文只记录当前首页的有效实现。10 月 17 日的试验与封板过程见 [Issue #302](https://github.com/montricwang/poeticus/issues/302)；阅读室排版是独立职责，不应照搬首页截断规则。

## 组件与数据

- `frontend/src/components/home-screen.tsx`（`HomeScreen`）：组合导航、推荐槽位、分割线和馆藏搜索；通过 `ResizeObserver` 测量推荐槽位，将剩余高度写入 `--home-classic-max-height`。每日推荐由上游 `featured` 提供，首页不生成另一套推荐或会话。
- `frontend/src/components/daily-recommendation.tsx`（`DailyRecommendation`）：排布印章与作品，印章点击后进入阅读室。手机端取两者横向组合的视觉中心；桌面端保留独立的三栏布局。
- `frontend/src/components/featured-poem-display.tsx`（`FeaturedPoemDisplay`、`ContinuousPoemBody`）：根据空间决定预览哪些完整片段，并将手机正文断为竖列。纯文本列划分由 `frontend/src/lib/home-preview-columns.ts` 的 `arrangeHomeColumns` 负责。
- `frontend/src/components/home-search.tsx`：馆藏搜索独立于每日推荐；首页搜索区靠近首屏底部。

开发环境 `import.meta.env.DEV` 下的「调试」菜单可以从 `frontend/src/lib/home-debug-poems.ts` 指定的十首实际作品中切换预览，或返回「今日推荐」。它不修改服务端每日推荐，生产构建不显示此入口。

## 已封板的手机竖屏设计（2026-10-17）

- 推荐槽位利用导航与底部搜索区之间的可用高度；推荐区、分割线和搜索区的间距由父级 `gap-4` 统一管理。推荐区不覆盖搜索，也不用 `position: fixed` 把搜索强行钉住。
- 作品和左侧「读这首词」印章作为一个整体水平居中，保留屏幕边缘安全留白；短作品自然收窄并留白。
- **正文最多五列**（`HOME_MAX_BODY_COLUMNS = 5`），不为填满而强制排成五列；设备实际宽高、标题和分片间距可以进一步减少列数。五列不是字数上限，也不按“小令 58 字”机械截断。纵向只受推荐槽位的实际高度预算约束。
- 优先展示全词；不够容纳时按顺序尝试完整的首片、后续完整片段。第一片仍无法容纳时，才向下取到可容纳的句号（`。！？`）等句界；确实放不下时存在更细的退路。被截断时标注「节选」，阅读室始终使用全文。
- 列数和节选**必须使用同一套物理预算与断列规则**：`getHomeMobileColumnBudget` 与 `arrangeHomeColumns`。不可用另一套宽度估算独立决定是否节选，避免出现可完整显示却被误判的情况。
- 当前移动断列模式以 `<1024px` 判断；这只是现行实现，不表示所有平板宽度及横屏已完成独立验收。桌面沿用另一种逐句竖排方式。

上述取舍已在 iPhone 17 上获得用户的阶段性视觉认可，不再继续主动调节正文列数、纵向字数或断列代价。**这是手机竖屏的阶段性封板，不是对所有极小屏、横屏或浏览器环境的全面验收。**

## 验证与已知边界

- 典型验证：手机宽度 320、390、402、430px，分别检查小令、中调、长调等十首样本；确认正文列数、全词或「节选」、印章加正文的中心位置，以及搜索区位置与横向溢出。桌面另行核对。
- 曾在 402px 手机视口发现《青玉案·元夕》误标「节选」：离屏测量克隆脱离 `#home`，丢失高度变量而误用较小的默认高度。修复措施是为克隆同步实际高度预算、去掉克隆时的旧高度，并在预算变化时重新测量。
- 317×446 等极小尺寸及横屏的推荐区/搜索区布局仍可能溢出，按 [Issue #302](https://github.com/montricwang/poeticus/issues/302) 或后续专门任务追踪，不把阶段性封板解释为已解决这些问题。
- 检查命令见 [开发者指南](../development.md)。自动检查、桌面 Playwright 不能代替真实 iPhone Safari 的视觉验收。
