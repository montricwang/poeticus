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
- 网页齿轮设置支持 Frontend、Backend、LangGraph、Retrieval、Reranker 的端口和附加启动参数。保存到本机 %LOCALAPPDATA% 下的 Poeticus/service-console/launch-options.json，下次启动生效。端口会自动转换为对应的 --port 参数，附加参数不能覆盖监听地址、端口或认证参数。
- 网页不开放任意 Shell / PowerShell 执行。程序路径和模型资产位置通过 Windows 安装目录的 settings.local.json 管理；更换基础命令尚不支持网页编辑。
- Windows：Reranker、Cloudflare Tunnel 启动参数固定，Cloudflare token 只从现有私有文件读取。
- MCP Manager：调用现有 MCP-Manager.ps1 的 Start / Stop，继续由原管理器维护四条隧道和巡检；网页当前展示 watch.log，Worker 的详细日志仍在 LocalMCPManager 目录中。
- 端口被非管理器进程占用会显示“外部运行”，不会重复启动或越权关闭。端口连通性不是完整的 HTTP 健康检查。
- WSL 停止会验证 Linux 进程组与运行时唯一标识；Windows 停止则核对 PID 与创建时间，只操作有归属的进程树。Windows 进程的首次停止使用 terminate / kill 机制，暂不保证应用层优雅退出。
- 仅在 127.0.0.1 监听，不允许公网访问；POST 要求运行时随机令牌、同源校验；网页只能管理预先定义的七种服务，不允许输入任意 Shell 命令。
- 当前不自动重启失败的服务，也不自动恢复关机前运行状态。

## 验证

在 Windows PowerShell 下的本目录：

    py -3.12 -m unittest discover -s tests -v
    py -3.12 server.py

测试使用短命假服务，**不会触碰真实 MCP、Cloudflare 或 RAG 服务**。UI 的真实端到端操作仍需打开浏览器人工检查。
