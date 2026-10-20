"""Windows-owned Poeticus development services. Requires psutil on Windows."""
from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.getenv("LOCALAPPDATA", str(ROOT))) / "Poeticus" / "service-console"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = ROOT / "settings.local.json"
DEFAULTS = {
    "wsl_distro": "Ubuntu",
    "wsl_project": "/home/montric/projects/poeticus",
    "cloudflared_exe": r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "reranker_exe": "",
    "reranker_model": "",
    "mcp_manager_script": "",
}


@dataclass(frozen=True)
class Service:
    id: str
    title: str
    environment: str
    port: int | None = None


SERVICES = [
    Service("frontend", "Frontend", "WSL2 · Vite", 5173),
    Service("backend", "Backend", "WSL2 · FastAPI", 8000),
    Service("langgraph", "LangGraph", "WSL2 · Agent", 2024),
    Service("retrieval", "Retrieval", "WSL2 · RAG", 8787),
    Service("reranker", "Reranker", "Windows · llama.cpp", 18081),
    Service("tunnel", "Cloudflare Tunnel", "Windows"),
    Service("mcp", "Local MCP Manager", "Windows · 4 tunnels"),
]
LOOKUP = {service.id: service for service in SERVICES}

WSL_SERVICE_IDS = frozenset(("frontend", "backend", "langgraph", "retrieval"))
CONFIGURABLE_SERVICES = frozenset((*WSL_SERVICE_IDS, "reranker", "tunnel", "mcp"))
FORBIDDEN_FLAGS = frozenset(("--port", "--host", "--api-token", "--token", "--token-file"))
INIT_PRESETS = frozenset(("venv", "venv-nvm", "venv-retrieval", "none"))


def read_config() -> dict:
    config = DEFAULTS.copy()
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("settings.local.json must be a JSON object")
        for key, value in data.items():
            if key in config and isinstance(value, str):
                config[key] = value
    return config


def port_open(port: int | None) -> bool:
    if port is None:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def process_for(record: dict | None) -> psutil.Process | None:
    if not record:
        return None
    try:
        process = psutil.Process(int(record["pid"]))
        if (abs(process.create_time() - float(record["created"])) < 0.1
                and process.is_running() and process.status() != psutil.STATUS_ZOMBIE):
            return process
    except (psutil.Error, ValueError, KeyError, TypeError):
        pass
    return None


class Supervisor:
    def __init__(self, *, state_dir: Path = STATE_DIR, config: dict | None = None):
        self.directory = state_dir
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config = config or read_config()
        self.state_file = self.directory / "owned.json"
        self.launch_file = self.directory / "launch-options.json"
        self.lock = threading.RLock()
        try:
            self.launch_options = json.loads(self.launch_file.read_text(encoding="utf-8"))
            if not isinstance(self.launch_options, dict):
                self.launch_options = {}
        except (FileNotFoundError, json.JSONDecodeError):
            self.launch_options = {}
        self.handles: dict[str, subprocess.Popen] = {}
        try:
            self.owned = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.owned = {}

    def _save(self):
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.owned, indent=2), encoding="utf-8")
        temp.replace(self.state_file)

    def _defaults_for(self, key: str) -> dict:
        cfg = self.config
        work = cfg["wsl_project"]
        windows_cwd = str(Path(os.getenv("SystemRoot", "C:\\\\Windows")) / "System32")
        base = {
            "frontend": ("npm", "--prefix frontend run dev -- --host 0.0.0.0", work, "venv-nvm"),
            "backend": ("uvicorn", "backend.app:app --reload", work, "venv"),
            "langgraph": ("langgraph", "dev", work, "venv-nvm"),
            "retrieval": ("python", "-m scripts.retrieval.run_serving --device cpu", work, "venv-retrieval"),
            "reranker": (
                cfg["reranker_exe"], shlex.join([
                    "-m", cfg["reranker_model"], "--reranking", "--pooling", "rank",
                    "--embedding", "-ngl", "99", "--host", "127.0.0.1", "-c", "2048"
                ]), str(Path(cfg["reranker_exe"]).parent), "none"
            ),
            "tunnel": (cfg["cloudflared_exe"], "tunnel run", windows_cwd, "none"),
            "mcp": ("powershell.exe", "-NoProfile -ExecutionPolicy Bypass", windows_cwd, "none"),
        }
        program, command_args, working_directory, initialization = base[key]
        return {
            "editable": True,
            "platform": "WSL" if key in WSL_SERVICE_IDS else "Windows",
            "distro": cfg["wsl_distro"] if key in WSL_SERVICE_IDS else "",
            "program": program,
            "command_args": command_args,
            "working_directory": working_directory,
            "initialization": initialization,
            "port": LOOKUP[key].port,
            "arguments": "",
            "script_path": cfg["mcp_manager_script"] if key == "mcp" else "",
        }

    def launch_settings(self, key: str) -> dict:
        """One effective runtime profile, layered over legacy settings and safe defaults."""
        default = self._defaults_for(key)
        saved = self.launch_options.get(key, {})
        if not isinstance(saved, dict):
            saved = {}
        settings = {**default, **{field: saved[field] for field in default if field in saved}}
        settings["preview"] = self._command_preview(key, settings)
        return settings

    def _command_preview(self, key: str, settings: dict) -> str:
        command = shlex.join([settings["program"], *shlex.split(settings["command_args"])])
        if key in WSL_SERVICE_IDS or key == "reranker":
            command += " --port " + str(settings["port"])
            if settings["arguments"]:
                command += " " + shlex.join(shlex.split(settings["arguments"]))
        if key == "tunnel":
            command += " --token-file <本机私有文件>"
        if key == "mcp":
            command += " -File " + shlex.quote(settings["script_path"]) + " -Action Start"
        return command

    def _validate_settings(self, key: str, value: dict) -> dict:
        defaults = self._defaults_for(key)
        editable_fields = {"program", "command_args", "working_directory", "initialization",
                           "distro", "port", "arguments", "script_path"}
        if not isinstance(value, dict) or not set(value) <= editable_fields:
            raise ValueError("启动配置包含未知字段")
        updated = {**self.launch_settings(key), **value}
        updated.pop("preview", None)
        # platform, editable and all runtime responsibility boundaries remain fixed.
        if not isinstance(updated["initialization"], str) or updated["initialization"] not in INIT_PRESETS:
            raise ValueError("未知环境初始化预设")
        if key not in WSL_SERVICE_IDS and updated["initialization"] != "none":
            raise ValueError("Windows 服务不能使用 WSL 初始化预设")
        if key in WSL_SERVICE_IDS and updated["initialization"] == "none":
            raise ValueError("WSL 服务必须明确选择初始化预设")
        for name in ("program", "command_args", "working_directory", "arguments", "distro", "script_path"):
            v = updated[name]
            if not isinstance(v, str) or len(v) > 1000 or "\\n" in v or "\\r" in v or "\\x00" in v:
                raise ValueError(f"{name} 不符合字符串长度与换行约束")
        if not updated["program"].strip() or not updated["working_directory"].strip():
            raise ValueError("执行程序与工作目录不能为空")
        if updated["port"] is None:
            if key not in ("mcp", "tunnel"):
                raise ValueError("端口不能为空")
        elif type(updated["port"]) is not int or not 1024 <= updated["port"] <= 65535:
            raise ValueError("端口必须是 1024–65535 的整数")
        if key in WSL_SERVICE_IDS and (not updated["working_directory"].startswith("/")
                                       or not updated["distro"].strip()):
            raise ValueError("WSL 工作目录应为绝对路径，发行版名称不能为空")
        if key not in WSL_SERVICE_IDS:
            if updated["distro"]:
                raise ValueError("Windows 服务不使用 WSL 发行版")
            if not Path(updated["working_directory"]).is_absolute():
                raise ValueError("Windows 工作目录需要绝对路径")
        for field in ("command_args", "arguments"):
            try:
                values = shlex.split(updated[field])
            except ValueError as exc:
                raise ValueError(f"{field} 的引号不完整") from exc
            if len(values) > 50:
                raise ValueError("单组命令参数不能超过 50 项")
            if key in WSL_SERVICE_IDS or key == "reranker":
                if any(token.split("=", 1)[0].lower() in FORBIDDEN_FLAGS for token in
                       shlex.split(updated["arguments"])):
                    raise ValueError("附加参数不可覆盖端口、监听地址或认证参数")
        if key in ("tunnel", "mcp"):
            # These integrations keep their own credential and lifecycle protocols.
            if updated["command_args"] != defaults["command_args"] or updated["arguments"]:
                raise ValueError("Tunnel / MCP 只允许编辑执行程序和工作目录，启动协议固定")
            if updated["port"] is not None:
                raise ValueError("Tunnel / MCP 没有通用监听端口")
        if key == "mcp":
            if not updated["program"].lower().endswith(("powershell.exe", "pwsh.exe")):
                raise ValueError("MCP Manager 必须由 PowerShell 运行")
            if not updated["script_path"].lower().endswith(".ps1"):
                raise ValueError("MCP Manager 脚本必须是 .ps1 文件")
        elif updated["script_path"]:
            raise ValueError("只有 MCP Manager 有单独脚本路径")
        return updated

    def update_launch_settings(self, key: str, value: dict) -> dict:
        if key not in CONFIGURABLE_SERVICES:
            raise ValueError("未知服务")
        with self.lock:
            if process_for(self.owned.get(key)) or (key == "mcp" and self._mcp_process()):
                raise ValueError("请先停止控制台管理的服务，再修改启动配置")
            updated = self._validate_settings(key, value)
            self.launch_options[key] = {field: updated[field] for field in
                ("program", "command_args", "working_directory", "initialization",
                 "distro", "port", "arguments", "script_path")}
            temp = self.launch_file.with_suffix(".tmp")
            temp.write_text(json.dumps(self.launch_options, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            temp.replace(self.launch_file)
            return self.launch_settings(key)

    def reset_launch_settings(self, key: str) -> dict:
        with self.lock:
            if process_for(self.owned.get(key)) or (key == "mcp" and self._mcp_process()):
                raise ValueError("请先停止控制台管理的服务，再恢复默认配置")
            self.launch_options.pop(key, None)
            temp = self.launch_file.with_suffix(".tmp")
            temp.write_text(json.dumps(self.launch_options, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            temp.replace(self.launch_file)
            return self.launch_settings(key)

    def _port(self, key: str) -> int | None:
        return self.launch_settings(key)["port"]

    def _args(self, key: str) -> list[str]:
        return shlex.split(self.launch_settings(key)["arguments"])

    def log_path(self, key: str) -> Path:
        if key == "mcp":
            return Path(os.getenv("LOCALAPPDATA", str(self.directory))) / "LocalMCPManager" / "watch.log"
        return self.directory / (key + ".log")

    def _mcp_process(self) -> psutil.Process | None:
        pid_file = Path(os.getenv("LOCALAPPDATA", str(self.directory))) / "LocalMCPManager" / "watch.pid"
        try:
            pid = int(pid_file.read_text(encoding="utf-8-sig").strip())
            process = psutil.Process(pid)
            args = " ".join(process.cmdline()).lower()
            expected_script = Path(self.launch_settings("mcp")["script_path"]).name.lower()
            if expected_script and expected_script in args and "watch" in args and process.is_running():
                return process
        except (ValueError, OSError, psutil.Error):
            pass
        return None

    def status(self, key: str) -> dict:
        service = LOOKUP[key]
        with self.lock:
            owned = process_for(self.owned.get(key))
        if key == "mcp":
            running = self._mcp_process()
            healthy = all(port_open(p) for p in (8080, 8081, 8082, 8083))
            state = "running" if running and healthy else "starting" if running else "external" if healthy else "stopped"
            pid = running.pid if running else None
        else:
            reachable = port_open(self._port(key))
            if owned:
                state = "running" if (reachable or self._port(key) is None) else "starting"
            else:
                state = "external" if reachable else "stopped"
            pid = owned.pid if owned else None
        return {
            "id": key, "title": service.title, "environment": service.environment,
            "port": self._port(key), "state": state, "pid": pid,
            "managed": bool(owned) if key != "mcp" else bool(self._mcp_process()),
        }

    def _build_command(self, key: str, run_id: str) -> list[str]:
        settings = self.launch_settings(key)
        program = settings["program"]
        params = shlex.split(settings["command_args"])
        extra = self._args(key)
        if key in WSL_SERVICE_IDS:
            pidfile = "$HOME/.cache/poeticus-service-console/" + key + "-" + run_id + ".pid"
            initialization = {
                "venv": "",
                "venv-nvm": (
                    'test -s "$HOME/.nvm/nvm.sh" || { echo "WSL NVM missing" >&2; exit 127; }; '
                    '. "$HOME/.nvm/nvm.sh"; nvm use --silent default >/dev/null; '
                    'case "$(command -v node || true):$(command -v npm || true)" in '
                    '/mnt/*|*:/mnt/*|:* ) echo "Linux Node/npm not found" >&2; exit 127;; esac; '
                ),
                "venv-retrieval": "source ~/.config/poeticus/retrieval.env; ",
            }[settings["initialization"]]
            command = shlex.join([program, *params, "--port", str(settings["port"]), *extra])
            worker = (
                "set -e; export POETICUS_CONSOLE_RUN_ID=" + shlex.quote(run_id) +
                "; printf '%s %s\\n' \"$$\" \"$POETICUS_CONSOLE_RUN_ID\" > \"" + pidfile + "\""
                "; cd " + shlex.quote(settings["working_directory"]) +
                " && source .venv/bin/activate && export PYTHONUNBUFFERED=1; " +
                initialization + "exec " + command
            )
            script = 'mkdir -p "$HOME/.cache/poeticus-service-console"; exec setsid -w bash -lc ' + shlex.quote(worker)
            return ["wsl.exe", "-d", settings["distro"], "--exec", "bash", "-lc", script]
        if key == "reranker":
            if not Path(program).is_file():
                raise ValueError("找不到 Reranker 可执行文件")
            if not any(name in params for name in ("-m", "--model")):
                raise ValueError("请配置 Reranker 模型路径 (-m)")
            return [program, *params, "--port", str(settings["port"]), *extra]
        if key == "tunnel":
            token_file = Path(os.environ["LOCALAPPDATA"]) / "Poeticus" / "secrets" / "cloudflare-tunnel.token"
            if not (Path(program).is_file() and token_file.is_file()):
                raise ValueError("找不到 cloudflared.exe 或私有 Tunnel Token 文件")
            return [program, "tunnel", "run", "--token-file", str(token_file)]
        if key == "mcp":
            script = settings["script_path"]
            if not script or not Path(script).is_file():
                raise ValueError("找不到 Local MCP Manager 脚本")
            return [program, *params, "-File", script, "-Action", "Start"]
        raise ValueError("未知服务")

    def start(self, key: str) -> str:
        with self.lock:
            now = self.status(key)
            if now["state"] != "stopped":
                return "已运行或端口被占用；没有重复启动"
            run_id = uuid.uuid4().hex
            args = self._build_command(key, run_id)
            settings_cwd = self.launch_settings(key)["working_directory"]
            if key not in WSL_SERVICE_IDS and not Path(settings_cwd).is_dir():
                raise ValueError("Windows 工作目录不存在：" + settings_cwd)
            log_path = self.directory / (key + ".log")
            with log_path.open("ab", buffering=0) as logfile:
                logfile.write(("\n=== start " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n").encode())
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                if key == "mcp":
                    completed = subprocess.run(args, stdin=subprocess.DEVNULL,
                        stdout=logfile, stderr=subprocess.STDOUT, timeout=50, check=False,
                        creationflags=flags)
                    if completed.returncode != 0:
                        raise RuntimeError(f"MCP Manager 启动失败（exit={completed.returncode}），请检查 mcp.log")
                    return "已调用 MCP Manager 启动与巡检"
                proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                    stdout=logfile, stderr=subprocess.STDOUT,
                    cwd=str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32") if os.name == "nt" else None,
                    creationflags=flags)
            self.handles[key] = proc
            record = {"pid": proc.pid, "created": psutil.Process(proc.pid).create_time(), "run_id": run_id}
            if key in WSL_SERVICE_IDS:
                record["pidfile"] = key + "-" + run_id + ".pid"
            self.owned[key] = record
            self._save()
            return "已发送启动命令"

    def _signal_wsl(self, key: str, run_id: str, signal: str,
                    pidfile_name: str | None = None) -> None:
        # Preserve the older pidfile name for processes launched by the original version.
        expected = key + "-" + run_id + ".pid"
        if pidfile_name is not None and pidfile_name != expected:
            raise ValueError("WSL PID 文件归属不匹配")
        pidfile = "$HOME/.cache/poeticus-service-console/" + (
            pidfile_name if pidfile_name else key + ".pid"
        )
        # A stale pidfile or reused Linux PID must not kill someone else's process.
        script = (
            "read -r pid token < \"" + pidfile + "\" || exit 11; "
            "test \"$token\" = " + shlex.quote(run_id) + " || exit 12; "
            "test \"$(ps -o pgid= -p \"$pid\" | tr -d ' ')\" = \"$pid\" || exit 13; "
            "tr '\\0' '\\n' < /proc/$pid/environ | grep -Fxq " +
            shlex.quote("POETICUS_CONSOLE_RUN_ID=" + run_id) + " || exit 14; "
            "kill -" + signal + " -- \"-$pid\""
        )
        completed = subprocess.run(["wsl.exe", "-d", self.launch_settings(key)["distro"], "--exec",
                        "bash", "-lc", script], timeout=12, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if completed.returncode != 0:
            raise RuntimeError("WSL 进程归属校验或终止信号失败；没有强制停止")

    @staticmethod
    def _stop_windows_tree(proc: psutil.Process) -> None:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            proc.terminate()
        except psutil.Error:
            pass
        _, alive = psutil.wait_procs([*children, proc], timeout=3)
        for item in alive:
            try:
                item.kill()
            except psutil.Error:
                pass

    def stop(self, key: str) -> str:
        with self.lock:
            if key == "mcp":
                args = self._build_command(key, "")
                args[-1] = "Stop"
                with (self.directory / "mcp.log").open("ab") as logfile:
                    subprocess.run(args, stdin=subprocess.DEVNULL, stdout=logfile,
                                   stderr=subprocess.STDOUT, timeout=40, check=False)
                return "已请求 MCP Manager 停止所管理的服务"
            record = self.owned.get(key)
            process = process_for(record)
            if process is None:
                self.owned.pop(key, None)
                self._save()
                return "没有可确认归属的运行进程；未终止外部程序"
            if key in WSL_SERVICE_IDS:
                self._signal_wsl(key, record["run_id"], "TERM", record.get("pidfile"))
                try:
                    process.wait(timeout=4)
                except psutil.TimeoutExpired:
                    # A service can ignore TERM; validate ownership again before KILL.
                    self._signal_wsl(key, record["run_id"], "KILL", record.get("pidfile"))
                    try:
                        process.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        self._stop_windows_tree(process)
            else:
                self._stop_windows_tree(process)
            handle = self.handles.pop(key, None)
            if handle:
                try:
                    handle.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    pass
            self.owned.pop(key, None)
            self._save()
            return "已停止所管理的进程"

    def restart(self, key: str) -> str:
        if self.status(key)["state"] == "external":
            return "端口由外部进程占用；不能重启"
        self.stop(key)
        return self.start(key)

    def all_statuses(self) -> list[dict]:
        return [self.status(s.id) for s in SERVICES]
