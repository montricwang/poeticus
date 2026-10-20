"""Windows-owned Poeticus development services. Requires psutil on Windows."""
from __future__ import annotations

import json
import os
import shlex
import shutil
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

WSL_COMMANDS = {
    "frontend": "exec npm --prefix frontend run dev -- --host 0.0.0.0",
    "backend": "exec uvicorn backend.app:app --reload",
    "langgraph": "exec langgraph dev",
    "retrieval": "source ~/.config/poeticus/retrieval.env && exec python -m scripts.retrieval.run_serving --device cpu",
}

CONFIGURABLE_SERVICES = frozenset((*WSL_COMMANDS, "reranker"))
FORBIDDEN_FLAGS = frozenset(("--port", "--host", "--api-token", "--token", "--token-file"))


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

    def launch_settings(self, key: str) -> dict:
        """Safe, editable options. Binary paths/secrets are never exposed over HTTP."""
        service = LOOKUP[key]
        saved = self.launch_options.get(key, {})
        if key not in CONFIGURABLE_SERVICES:
            return {"editable": False, "port": service.port, "arguments": ""}
        port = saved.get("port", service.port)
        args = saved.get("arguments", "")
        return {"editable": True, "port": port, "arguments": args}

    def update_launch_settings(self, key: str, value: dict) -> dict:
        if key not in CONFIGURABLE_SERVICES:
            raise ValueError("此服务使用固定启动命令，不能在网页修改")
        if not isinstance(value, dict) or set(value) != {"port", "arguments"}:
            raise ValueError("只能配置端口和附加参数")
        port, arguments = value["port"], value["arguments"]
        if type(port) is not int or not (1024 <= port <= 65535):
            raise ValueError("端口必须是 1024–65535 的整数")
        if not isinstance(arguments, str) or len(arguments) > 500:
            raise ValueError("启动参数长度不得超过 500 字符")
        try:
            tokens = shlex.split(arguments, posix=True)
        except ValueError as exc:
            raise ValueError("启动参数的引号不完整") from exc
        if len(tokens) > 30 or any(
            token.split("=", 1)[0].lower() in FORBIDDEN_FLAGS for token in tokens
        ):
            raise ValueError("附加参数不可覆盖端口、监听地址或认证参数")
        with self.lock:
            if process_for(self.owned.get(key)):
                raise ValueError("请先停止控制台管理的服务，再修改启动配置")
            self.launch_options[key] = {"port": port, "arguments": arguments}
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
            if "mcp-manager.ps1" in args and "watch" in args and process.is_running():
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
                state = "running" if (reachable or service.port is None) else "starting"
            else:
                state = "external" if reachable else "stopped"
            pid = owned.pid if owned else None
        return {
            "id": key, "title": service.title, "environment": service.environment,
            "port": self._port(key), "state": state, "pid": pid,
            "managed": bool(owned) if key != "mcp" else bool(self._mcp_process()),
        }

    def _build_command(self, key: str, run_id: str) -> list[str]:
        cfg = self.config
        if key in WSL_COMMANDS:
            project = shlex.quote(cfg["wsl_project"])
            pidfile = "$HOME/.cache/poeticus-service-console/" + key + ".pid"
            port = self._port(key)
            extra = " ".join(shlex.quote(arg) for arg in self._args(key))
            # Login-style non-interactive WSL shells do not load .bashrc / NVM by default.
            # Ensure node/npm are Linux binaries rather than Windows npm on the inherited PATH.
            node_init = (
                'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
                '. "$HOME/.nvm/nvm.sh" && nvm use --silent default >/dev/null; fi; '
            )
            if key == "frontend":
                node_init += (
                    'case "$(command -v node || true):$(command -v npm || true)" in '
                    '/mnt/*|*:/mnt/*|:* ) echo "Linux Node/npm not found; configure WSL NVM" >&2; exit 127;; esac; '
                )
            command = WSL_COMMANDS[key] + " --port " + str(port)
            if extra:
                command += " " + extra
            worker = (
                "set -e; export POETICUS_CONSOLE_RUN_ID=" + shlex.quote(run_id) +
                "; printf '%s %s\\n' \"$$\" \"$POETICUS_CONSOLE_RUN_ID\" > \"" + pidfile + "\""
                "; cd " + project + " && source .venv/bin/activate && "
                "export PYTHONUNBUFFERED=1; " + node_init + command
            )
            script = "mkdir -p \"$HOME/.cache/poeticus-service-console\"; exec setsid -w bash -lc " + shlex.quote(worker)
            return ["wsl.exe", "-d", cfg["wsl_distro"], "--exec", "bash", "-lc", script]
        if key == "reranker":
            exe, model = cfg["reranker_exe"], cfg["reranker_model"]
            if not (Path(exe).is_file() and model):
                raise ValueError("请先在 settings.local.json 配置 reranker_exe 和 reranker_model")
            return [exe, "-m", model, "--reranking", "--pooling", "rank", "--embedding",
                    "-ngl", "99", "--host", "127.0.0.1", "--port", str(self._port(key)), "-c", "2048",
                    *self._args(key)]
        if key == "tunnel":
            exe = cfg["cloudflared_exe"] or shutil.which("cloudflared")
            token_file = Path(os.environ["LOCALAPPDATA"]) / "Poeticus" / "secrets" / "cloudflare-tunnel.token"
            if not (exe and Path(exe).is_file() and token_file.is_file()):
                raise ValueError("找不到 cloudflared.exe 或私有 tunnel token 文件")
            return [str(exe), "tunnel", "run", "--token-file", str(token_file)]
        if key == "mcp":
            path = cfg["mcp_manager_script"]
            if not path or not Path(path).is_file():
                raise ValueError("请先配置 mcp_manager_script")
            return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", path, "-Action", "Start"]
        raise ValueError("未知服务")

    def start(self, key: str) -> str:
        with self.lock:
            now = self.status(key)
            if now["state"] != "stopped":
                return "已运行或端口被占用；没有重复启动"
            run_id = uuid.uuid4().hex
            args = self._build_command(key, run_id)
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
            self.owned[key] = {"pid": proc.pid, "created": psutil.Process(proc.pid).create_time(), "run_id": run_id}
            self._save()
            return "已发送启动命令"

    def _signal_wsl(self, key: str, run_id: str, signal: str) -> None:
        pidfile = "$HOME/.cache/poeticus-service-console/" + key + ".pid"
        # A stale pidfile or reused Linux PID must not kill someone else's process.
        script = (
            "read -r pid token < \"" + pidfile + "\" || exit 11; "
            "test \"$token\" = " + shlex.quote(run_id) + " || exit 12; "
            "test \"$(ps -o pgid= -p \"$pid\" | tr -d ' ')\" = \"$pid\" || exit 13; "
            "tr '\\0' '\\n' < /proc/$pid/environ | grep -Fxq " +
            shlex.quote("POETICUS_CONSOLE_RUN_ID=" + run_id) + " || exit 14; "
            "kill -" + signal + " -- \"-$pid\""
        )
        completed = subprocess.run(["wsl.exe", "-d", self.config["wsl_distro"], "--exec",
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
            if key in WSL_COMMANDS:
                self._signal_wsl(key, record["run_id"], "TERM")
                try:
                    process.wait(timeout=4)
                except psutil.TimeoutExpired:
                    # A service can ignore TERM; validate ownership again before KILL.
                    self._signal_wsl(key, record["run_id"], "KILL")
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
