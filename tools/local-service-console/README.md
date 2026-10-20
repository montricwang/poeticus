# Poeticus 本地服务控制台（Windows MVP）

在同一个本地网页管理 Poeticus 的 Vite、FastAPI、LangGraph、Retrieval、Reranker、Cloudflare Tunnel，以及现有 Local MCP Manager。它与 Poeticus API 独立运行，不需要启动产品前后端。

## 首次配置

1. 安装 Windows Python 3.12 和 psutil（本机已安装则跳过）：运行 py -3.12 -m pip install psutil。
2. 将 settings.example.json 复制为 settings.local.json，并按本机实际路径配置 Reranker 和 MCP Manager 的可执行文件位置。该文件已被 Git 忽略；不要把任何密钥明文写入它。
3. Windows PowerShell 中运行 powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\install.ps1，将独立程序复制到当前用户的本地应用目录，并创建桌面快捷方式 Poeticus Control。
4. 双击桌面快捷方式，打开 http://127.0.0.1:8765。或在本目录执行 py -3.12 server.py 观察启动错误。
5. 如果日后希望登录 Windows 后自动启动控制台，可使用 Windows 任务计划程序，在**当前用户登录后**启动 pythonw.exe server.py --no-browser。请先通过真实手动验证再启用；不要注册成 SYSTEM 服务，因为 WSL 和用户配置依赖登录用户。

关闭网页不会停止已托管的进程。终端输出写入 %LOCALAPPDATA%\Poeticus\service-console\*.log。网页通过 SSE 显示增量日志，刷新后仍可读取历史尾部。管理器自己的控制状态存到同目录 owned.json，停止时核对进程创建时间，避免错误结束重复使用 PID 的进程。

## 服务边界与限制

- WSL：Frontend、Backend、LangGraph、Retrieval 使用 WSL 内项目的 .venv，Retrieval 读取 WSL 私有环境文件；启动 Vite 不重复执行 npm ci。Windows 发起的非交互式 WSL 会显式加载 NVM 并选取默认 Linux Node.js，避免 Windows npm 的 UNC 错误；Linux Node/npm 不存在时，Frontend 将直接报错。
- 网页齿轮可以修改完整的可信启动定义；详细字段、固定协议及恢复默认规则见下方“高级启动配置”。
- Windows：Reranker 的程序/模型参数可调整，Cloudflare Token 始终从现有私有文件读取。
- MCP Manager：调用现有 MCP-Manager.ps1 的 Start / Stop，继续由原管理器维护四条隧道和巡检；网页当前展示 watch.log，Worker 的详细日志仍在 LocalMCPManager 目录中。
- 端口被非管理器进程占用会显示“外部运行”，不会重复启动或越权关闭。端口连通性不是完整的 HTTP 健康检查。
- WSL 每次启动使用独立 PID 文件（旧进程的原路径仍兼容），停止会验证 Linux 进程组与运行时唯一标识；Windows 停止则核对 PID 与创建时间，只操作有归属的进程树。Windows 进程的首次停止使用 terminate / kill 机制，暂不保证应用层优雅退出。
- 仅在 127.0.0.1 监听，不允许公网访问；POST 要求运行时随机令牌、同源校验；网页只能管理预先定义的七种服务，不允许输入任意 Shell 命令。
- 当前不自动重启失败的服务，也不自动恢复关机前运行状态。

## 验证

在 Windows PowerShell 下的本目录：

    py -3.12 -m unittest discover -s tests -v
    py -3.12 server.py

测试使用短命假服务，**不会触碰真实 MCP、Cloudflare 或 RAG 服务**。UI 的真实端到端操作仍需打开浏览器人工检查。

## 高级启动配置（2026-10-20）

- 七项服务均可在网页查看启动程序、基础参数、工作目录和初始化预设；Windows / WSL 运行平台由进程管理器确定，不支持互换。
- Frontend、Backend、LangGraph、Retrieval、Reranker 可修改执行程序、基础参数、工作目录、端口、附加参数以及 WSL 初始化预设、发行版。
- Cloudflare Tunnel 的启动协议和私有 Token 文件固定，MCP Manager 仍委托现有 PowerShell 脚本执行 Start / Stop。两者允许更换程序与工作目录，MCP 还支持修改脚本路径。
- 受管服务运行时禁止修改或恢复配置；配置变更只对下次启动生效。单项“恢复默认”不影响其他服务。
- 配置保存在当前用户的 LocalAppData / Poeticus / service-console / launch-options.json。旧 port / arguments 配置仍能读取；新增字段缺失时使用默认值。
- 可编辑可执行程序意味着本机所有者可有意运行其他本地程序。请只填可信路径；网页不允许注入原始 Shell 初始化脚本。WSL 初始化仅限固定预设，CLI 参数使用转义，Windows 使用参数列表启动。
