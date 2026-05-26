#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LANDING_PATH = ROOT / "launcher" / "index.html"
HOST = "127.0.0.1"
LAUNCHER_PORT = int(os.getenv("LLM_FORFILES_LAUNCHER_PORT", "8765"))
BACKEND_PORT = int(os.getenv("LLM_FORFILES_BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("LLM_FORFILES_FRONTEND_PORT", str(BACKEND_PORT)))
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_MODEL = os.getenv("OLLAMA_TOPIC_MODEL", "qwen2.5:3b")
VENV_DIR = ROOT / ".venv"

STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "running": False,
    "done": False,
    "failed": False,
    "percent": 0,
    "phase": "idle",
    "message": "Aguardando start",
    "detail": "",
    "logs": [],
    "frontend_url": f"http://{HOST}:{BACKEND_PORT}",
    "backend_url": f"http://{HOST}:{BACKEND_PORT}",
}
PROCESSES: dict[str, subprocess.Popen] = {}


def log(phase: str, percent: float, message: str, detail: str = "") -> None:
    with STATE_LOCK:
        STATE.update(
            {
                "phase": phase,
                "percent": max(0, min(100, round(percent, 1))),
                "message": message,
                "detail": detail,
            }
        )
        STATE["logs"].append(
            {
                "time": time.strftime("%H:%M:%S"),
                "phase": phase,
                "percent": STATE["percent"],
                "message": message,
                "detail": detail,
            }
        )
        STATE["logs"] = STATE["logs"][-160:]


def run_startup() -> None:
    with STATE_LOCK:
        if STATE["running"]:
            return
        STATE.update({"running": True, "done": False, "failed": False, "logs": []})

    try:
        log("python", 4, "Preparando ambiente Python local", str(VENV_DIR))
        python_bin = ensure_virtualenv()
        log("python", 10, "Instalando dependencias no virtualenv", "pip install -e .")
        run_command([str(python_bin), "-m", "pip", "install", "-e", "."], ROOT, 10, 18)

        log("ollama", 20, "Verificando Ollama", "Procurando binario e API local")
        ensure_ollama_installed()
        ensure_ollama_running()
        ensure_ollama_model()

        log("frontend", 62, "Verificando frontend buildado", "frontend/dist")
        ensure_frontend_dist()

        log("backend", 82, "Iniciando backend", f"porta {BACKEND_PORT}")
        ensure_backend_running(python_bin)

        app_url = f"http://{HOST}:{BACKEND_PORT}/app"
        log("open", 98, "Abrindo app", app_url)
        webbrowser.open(app_url)

        log("ready", 100, "App pronto", f"App: {app_url} · Backend API: http://{HOST}:{BACKEND_PORT}")
        with STATE_LOCK:
            STATE.update({"running": False, "done": True})
    except Exception as exc:  # noqa: BLE001 - launcher should surface operational failures.
        log("failed", STATE.get("percent", 0), "Falha ao iniciar", str(exc))
        with STATE_LOCK:
            STATE.update({"running": False, "failed": True})


def ensure_virtualenv() -> Path:
    python_bin = venv_python()
    if not python_bin.exists():
        log("python", 5, "Criando virtualenv", f"{sys.executable} -m venv {VENV_DIR}")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Nao foi possivel criar o virtualenv local. "
                "Em Ubuntu/Debian instale: sudo apt install python3-venv. "
                f"Saida: {compact(result.stdout)}"
            )

    if not command_ok([str(python_bin), "-m", "pip", "--version"]):
        log("python", 7, "Instalando pip no virtualenv", "ensurepip")
        result = subprocess.run(
            [str(python_bin), "-m", "ensurepip", "--upgrade"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not command_ok([str(python_bin), "-m", "pip", "--version"]):
            raise RuntimeError(f"Virtualenv criado, mas pip nao ficou disponivel. Saida: {compact(result.stdout)}")

    log("python", 9, "Virtualenv pronto", str(python_bin))
    return python_bin


def venv_python() -> Path:
    if platform.system().lower() == "windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def command_ok(command: list[str]) -> bool:
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0
    except OSError:
        return False

def ensure_ollama_installed() -> None:
    if shutil.which("ollama"):
        log("ollama", 24, "Ollama encontrado", shutil.which("ollama") or "")
        return

    if platform.system().lower() != "linux":
        raise RuntimeError("Ollama nao encontrado. Instalacao automatica foi implementada apenas para Linux.")

    log("ollama", 25, "Instalando Ollama", "Baixando instalador oficial de https://ollama.com/install.sh")
    installer_url = "https://ollama.com/install.sh"
    with urllib.request.urlopen(installer_url, timeout=60) as response:
        script = response.read()

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix="-ollama-install.sh") as file:
        file.write(script)
        temp_script = Path(file.name)

    try:
        temp_script.chmod(0o700)
        run_command(["sh", str(temp_script)], ROOT, 26, 36)
    finally:
        temp_script.unlink(missing_ok=True)

    if not shutil.which("ollama"):
        raise RuntimeError("O instalador terminou, mas o comando ollama ainda nao apareceu no PATH. Abra um novo terminal ou instale manualmente.")


def ensure_ollama_running() -> None:
    if http_ok(f"http://{HOST}:{OLLAMA_PORT}/api/tags"):
        log("ollama", 38, "Ollama ja esta rodando", f"http://{HOST}:{OLLAMA_PORT}")
        return

    log("ollama", 39, "Executando Ollama em background", "ollama serve")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    PROCESSES["ollama"] = proc

    wait_for_http(f"http://{HOST}:{OLLAMA_PORT}/api/tags", 45, "Ollama nao respondeu em 45s")
    log("ollama", 46, "Ollama online", f"http://{HOST}:{OLLAMA_PORT}")


def ensure_ollama_model() -> None:
    models = get_ollama_models()
    if OLLAMA_MODEL in models:
        log("model", 50, "Modelo Ollama ja instalado", OLLAMA_MODEL)
        return

    log("model", 51, "Baixando modelo Ollama", f"ollama pull {OLLAMA_MODEL}")
    run_command(["ollama", "pull", OLLAMA_MODEL], ROOT, 52, 60)
    log("model", 61, "Modelo pronto", OLLAMA_MODEL)


def get_ollama_models() -> set[str]:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{OLLAMA_PORT}/api/tags", timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return set()
    return {item.get("name", "") for item in payload.get("models", [])}


def ensure_backend_running(python_bin: Path) -> None:
    if http_ok(f"http://{HOST}:{BACKEND_PORT}/health"):
        if http_ok(f"http://{HOST}:{BACKEND_PORT}/app"):
            log("backend", 90, "Backend ja esta rodando", f"http://{HOST}:{BACKEND_PORT}")
            return
        raise RuntimeError(
            f"Ja existe um backend antigo rodando em http://{HOST}:{BACKEND_PORT}, mas ele nao esta servindo o frontend. "
            "Pare esse processo antigo e clique Start app novamente. Exemplo: pkill -f 'uvicorn backend.app.main:app'."
        )

    env = os.environ.copy()
    env.setdefault("OLLAMA_TOPIC_MODEL", OLLAMA_MODEL)
    env.setdefault("OLLAMA_LLM_MODEL", OLLAMA_MODEL)
    proc = subprocess.Popen(
        [str(python_bin), "-m", "uvicorn", "backend.app.main:app", "--host", HOST, "--port", str(BACKEND_PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    PROCESSES["backend"] = proc
    wait_for_http(f"http://{HOST}:{BACKEND_PORT}/health", 45, "Backend nao respondeu em 45s")
    log("backend", 94, "Backend online", f"http://{HOST}:{BACKEND_PORT}")


def ensure_frontend_dist() -> None:
    dist = ROOT / "frontend" / "dist"
    index = dist / "index.html"
    if index.exists():
        log("frontend", 74, "Frontend buildado encontrado", str(index))
        return

    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("frontend/dist nao existe e npm nao foi encontrado. Gere o pacote em uma maquina com Node usando scripts/build_portable.py.")

    log("frontend", 64, "Atualizando dependencias frontend", "npm install")
    run_command([npm, "install"], ROOT / "frontend", 64, 70)

    log("frontend", 70, "Gerando build frontend", "npm run build")
    run_command([npm, "run", "build"], ROOT / "frontend", 70, 78)

    if not index.exists():
        raise RuntimeError("Build do frontend terminou, mas frontend/dist/index.html nao foi encontrado.")


def run_command(command: list[str], cwd: Path, start_percent: float, end_percent: float) -> None:
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    last_line = ""
    for index, line in enumerate(proc.stdout, start=1):
        last_line = line.strip()
        percent = min(end_percent, start_percent + (index % 20) / 20 * (end_percent - start_percent))
        log("command", percent, "Executando comando", compact(last_line))
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Comando falhou ({code}): {' '.join(command)}\n{last_line}")
    log("command", end_percent, "Comando concluido", " ".join(command))


def wait_for_http(url: str, timeout_seconds: int, error: str) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if http_ok(url):
            return
        time.sleep(0.8)
    raise RuntimeError(error)


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def compact(value: str, limit: int = 240) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/index.html"):
            self.send_file(LANDING_PATH, "text/html; charset=utf-8")
            return
        if self.path == "/api/status":
            self.send_json(snapshot())
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/start":
            threading.Thread(target=run_startup, daemon=True).start()
            self.send_json({"started": True})
            return
        self.send_error(404)

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def snapshot() -> dict[str, Any]:
    with STATE_LOCK:
        return json.loads(json.dumps(STATE))


def find_free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((HOST, port)) != 0:
                return port
    return start


def main() -> None:
    global LAUNCHER_PORT
    LAUNCHER_PORT = find_free_port(LAUNCHER_PORT)
    server = ThreadingHTTPServer((HOST, LAUNCHER_PORT), Handler)
    url = f"http://{HOST}:{LAUNCHER_PORT}"
    print(f"Launcher aberto em {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando launcher")


if __name__ == "__main__":
    main()
