# 代码问题复盘

这里只收录**已修复且容易重犯**的工程问题，不记录测试输出或每日调试过程。先修复、复测，再决定是否沉淀；同类问题更新旧条目，优先把预防落实到代码检查或回归测试。执行流程见 [开发者指南](development.md)。

## 入场动画不能无限等待字体就绪

- **现象与原因**：首页和阅读室先以 `opacity: 0` 等待 `document.fonts.ready`，某个字体加载迟滞时 Promise 长时间未完成，诗文已在 DOM 中却一直看不见（[#323](https://github.com/montricwang/poeticus/issues/323)）。
- **预防方法**：影响内容可见性的字体/动画就绪等待必须有限时，并在超时后显示真实内容；字体加载完成后可按既有测量机制重新排版，不可把显示权限永久交给网络请求。
- **验证方式**：Playwright 在页面初始化前将 `document.fonts.ready` 模拟为不完成的 Promise；分别验证手机首次首页、直达阅读室和阅读室返回首页的最终透明度及搜索区可交互状态。

## 浏览器测试的离屏副本干扰选择器

- **现象与原因**：首页推荐诗文的离屏测量会临时复制 DOM，宽泛的 `.home-featured-poem header` 同时命中屏幕上的内容与隐藏副本，Playwright 因 strict mode 失败（[#303](https://github.com/montricwang/poeticus/pull/303)）。
- **预防方法**：交互测试定位到真实可见的语义容器（如 `getByRole('region', { name: '推荐作品' })`），不要依赖可能匹配隐藏探针的全局 CSS 选择器。
- **验证方式**：在真实浏览器运行推荐区的桌面/移动 Playwright 用例，确保无重复 locator；只跑 TypeScript 编译不够。

## 离屏测量未继承实际容器的 CSS 约束

- **现象与原因**：测量用的 `article` 克隆挂到 `document.body`，因此不再继承首页 `#home` 的 `--home-classic-max-height`。真实手机区域足够展示《青玉案》全词，克隆却按默认 18rem 高度计算出过大的横向宽度，导致错误「节选」（[#302](https://github.com/montricwang/poeticus/issues/302)）。克隆还可能保留上次排版留下的固定高度。
- **预防方法**：凡是脱离原容器的隐藏探针，必须核对实际继承的 CSS 变量、计算后的几何尺寸、动态高度变化；能共用物理预算和断列算法，就不要让测量与实际排版各自得出结论。
- **验证方式**：用同一首词在真实推荐槽位和离屏探针下比较宽度；在 320/390/402/430px 改变视口与内容后，确认实际正文列数不超过上限、是否完整展示与「节选」一致。

## Safari 竖排与 Flex 的物理宽度不能靠两套规则对齐

- **现象与原因**：桌面首页将整个 `article` 设为 `writing-mode: vertical-rl`，JS 根据离屏副本或 `line-height` 估计横向宽度，再用 `width`、`w-max`、`max-w-full` 与 Flex 收缩组合排列。在真实 iPad Safari 出现左侧整列被裁、短词印章离正文太远、长词印章压进正文；Chrome 的几何断言却曾全部通过（[#327](https://github.com/montricwang/poeticus/issues/327)）。删除 `overflow-hidden` 只会暴露内部超宽，不能修复父子尺寸分歧。
- **预防方法**：先划清物理布局与文字书写方向的职责。桌面预览的外层用普通横向 `row-reverse` Flex，只有题署和每条正文列使用 `vertical-rl`，正文列明确宽度；根据同一份列宽预算选择完整诗句，再让浏览器按可见内容自然组合印章和作品。禁止用额外的居中坐标、固定文章宽度或裁切掩盖结构问题。手机端封板算法保持独立。
- **验证方式**：短词《杨柳枝》和长词《戚氏》均检查真实标题/正文列的左、右矩形边界、印章与诗文 12px 间距、组合中心、视口边界和每列实际宽度；在 1024/1194/1440 等断点核对。Chrome/自动测试不能替代真实 iPad Safari 的最终验收。

## 共享题名字体只在部分视图复用

- **现象与原因**：阅读室桌面目录已有 `.poeticus-catalog-title`，保证题名中点 `·` 占一个汉字宽度；后来首页搜索结果和目录的手机抽屉分支忘记使用该样式，同一题名显示不一致（[#308](https://github.com/montricwang/poeticus/issues/308)）。
- **预防方法**：改动共享视觉规则时，搜全站使用该领域字段（如 `poemLabel`）的所有渲染分支；组件复用、CSS 类复用及“仅复用格式数据”是不同事情，不强行共用不适合的整张列表。
- **验证方式**：桌面目录、手机目录抽屉及首页结果分别确认字体；在浏览器实际测量中点与汉字的宽度比例，并保留 E2E 断言。

## 自定义清除按钮与浏览器原生控件重叠

- **现象与原因**：首页 `type="search"` 输入框会带 WebKit 自带的清除 X，旁边又显式渲染 Lucide X，结果出现两个按钮（[#308](https://github.com/montricwang/poeticus/issues/308)）。`autocomplete="off"` 不负责控制原生清除按钮。
- **预防方法**：设计输入控件时检查浏览器自带的 UI 与项目绘制的控件是否重复；当前首页使用 `type="text"` + `role="searchbox"`、`inputMode="search"`、`enterKeyHint="search"`，保留搜索语义、搜索键盘与本站唯一清除按钮。
- **验证方式**：手机／桌面实际输入后只有一个清除按钮，点击能清空内容，Enter／搜索键仍能提交表单；对 Safari 的软键盘另做真机核对。

## 自动化输入必须等待入场结束后的可交互状态

- **现象与原因**：首页首次入场期间，搜索区先以 `inert` 阻止焦点和输入。旧 Playwright 测试在页面刚载入时立即 `fill('苏轼')`，API 未报告失败，但 DOM 输入值仍为空；点击搜索后没有任何结果，导致二十余项后续断言一起失败（[#319](https://github.com/montricwang/poeticus/issues/319)、PR #321）。这是测试时序不符合交互契约，不应通过提前移除 `inert` 或放宽结果断言蒙混过去。
- **预防方法**：有入场锁定、加载遮罩或 disabled 状态的控件，先等待真实可交互条件（如 `inert` 解除），再执行 Playwright 用户动作；输入后立即验证实际 value 已更新。一个根因造成批量失败时先检查共同前置条件，不逐条延长 timeout。
- **验证方式**：对比页面刚加载时的 `inert` / `input.value`，与解除 `inert` 后输入、清除按钮和结果区是否正常；CI 重新运行真实浏览器 E2E。

## 动画中间帧闪动、临时滚动条与意外重播

- **现象与原因**：首页搜索的 FLIP 使用了 `delay`，但未设置 WAAPI 的 backwards fill，搜索框在延迟期间先闪到新布局的最终位置，再跳回起点上移；首页推荐词列通过 `translateY(6px)` 淡入，桌面正文横向滚动容器同时允许纵向滚动，动画中临时增加 6px `scrollHeight`，出现闪一下的竖向滚动条（[#308](https://github.com/montricwang/poeticus/issues/308)、[#319](https://github.com/montricwang/poeticus/issues/319)）。
- **预防方法**：为有延迟的 WAAPI 布局过渡检查 `fill`，确保延迟期间仍显示动画起点；检查位移动画是否暂时扩张滚动范围，滚动方向只保留产品需要的轴。不要仅凭动画结束后页面没有溢出就判定正常。
- **验证方式**：逐帧检查 0ms、延迟末尾、移动中、结束后的实际 `getBoundingClientRect()`、computed `transform`、`scrollHeight - clientHeight`、可见滚动条；桌面和手机各抽样，多首短词/长调都要覆盖。动画结束后重新调整窗口、字体加载及主题切换，核对动画不会无故重播。

## 前端动画回归必须观察全过程

- **现象与原因**：旧测试主要检查「提交后出现结果」「清除后推荐可见」，漏掉延迟期间闪动、临时滚动条、推荐与搜索框重叠、入场播放过快及重复触发等动态问题。缩短首页入场时还发现桌面诗行最晚错峰到 640ms 才播完，React 却在 605ms 撤下入场 class，末列可能突然跳到终点（[#325](https://github.com/montricwang/poeticus/issues/325)）。
- **预防方法**：每项入场/退出动效至少核对起点、25%、50%、75%、终点，以及前后状态。压缩串行动画时，须分别按真实手机/桌面 DOM 计算各项 `animation-delay + animation-duration` 的最大值，确保撤下动画 class 的时机晚于最后一项完成。测试必须区分可测异常（位置跳变、溢出、隐藏状态、交互阻塞、重复动画）和主观审美（节奏、舒适度）。优先把确定性问题写入浏览器 E2E，真实截图/录像逐步对照，不能只看截图的最终静止画面。
- **验证方式**：测试用浏览器真实运行并抽查中间帧的位移与透明度，检查 `prefers-reduced-motion`、重复操作、窗口 resize、浏览器前进/后退和组件重渲染；CI 绿不能替代 iPhone Safari 的实际键盘、滚动及观感验收。

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

## 展示测试把实现细节或旧几何假设当作契约

- **现象与原因**：书名分段让 `buildPoemTextRuns(text)` 改为 `buildPoemTextRuns(value)`，旧源码断言因形参名改变而误报；E2E 仍要求波浪线与文字盒子的间距非负，忽略为贴近字形而增加的 `translateX(0.2em)`，也在 CI 失败（PR #300）。10 月 17 日搜索框入场为分割线新增 `home-search-intro-divider` class 后，`home-first-screen.test.mjs` 仍以完整旧 `className` 匹配 JSX，导致 73 项 Node 测试中 1 项失败；更新断言后恢复通过。
- **预防方法**：优先检查稳定的渲染行为及正文列宽；源码断言不要绑定局部变量名，几何断言需区分盒子间距与应用 transform 后的视觉位置，设计调整时同步更新回归基准。
- **验证方式**：`cd frontend && node --experimental-strip-types --test tests/*.test.mjs`；PR 浏览器 CI 在桌面/手机验证最终书名线位置、正文列宽与阅读室隔离。


## 视觉微调没有权威参数入口，后来误当作布局补丁

- **现象与原因**：首页经过多轮调试，作者额外下移 2px、印章和节选字距、中国红及正文大小散落于 TSX；JS 还独立写了一份 CSS 的 0.9 换片间距。后续改 Safari 时，容易误改已确认审美方案。
- **预防方法**：跨组件复用、影响实际测量或反复微调的尺寸集中到 index.css 的语义作用域。光学校正命名并解释原因；不为每个局部 px 建全局 token，也不把 AI 提议写成用户审美硬约束。
- **验证方式**：搬迁前后核对 computed 样式、真实盒子边界、短词/长词与 1024px 断点。iPad Safari 另由真机验收。见 [前端视觉与排版规范](design/frontend-visual-conventions.md)。
