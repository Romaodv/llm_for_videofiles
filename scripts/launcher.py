#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LANDING_PATH = ROOT / "launcher" / "index.html"
HOST = "127.0.0.1"
LAUNCHER_PORT = int(os.getenv("LLM_FORFILES_LAUNCHER_PORT", "8765"))
BACKEND_PORT = int(os.getenv("LLM_FORFILES_BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("LLM_FORFILES_FRONTEND_PORT", str(BACKEND_PORT)))
VENV_DIR = ROOT / ".venv"
LOCAL_TOOLS_DIR = ROOT / ".local_tools"
FFMPEG_URL = os.getenv("LLM_FORFILES_FFMPEG_URL", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
LOCAL_FFMPEG_DIR = LOCAL_TOOLS_DIR / "ffmpeg"

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


def append_log(phase: str, message: str, detail: str = "") -> None:
    with STATE_LOCK:
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

        log("media", 20, "Verificando FFmpeg", "Necessario para audio/video local")
        ensure_ffmpeg_available()

        log("frontend", 24, "Verificando frontend buildado", "frontend/dist")
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


def ensure_ffmpeg_available() -> None:
    existing = shutil.which("ffmpeg")
    if existing:
        log("media", 23, "FFmpeg encontrado", existing)
        return

    local_ffmpeg = find_local_ffmpeg()
    if local_ffmpeg:
        add_to_path(local_ffmpeg.parent)
        log("media", 23, "FFmpeg local configurado", str(local_ffmpeg))
        return

    if platform.system().lower() != "windows":
        log("media", 23, "FFmpeg nao encontrado", "Instale ffmpeg no PATH se precisar converter video para o navegador")
        return

    if install_ffmpeg_with_winget_windows():
        return

    download_ffmpeg_windows()
    local_ffmpeg = find_local_ffmpeg()
    if not local_ffmpeg:
        raise RuntimeError("FFmpeg foi baixado, mas ffmpeg.exe nao foi encontrado no pacote extraido.")

    add_to_path(local_ffmpeg.parent)
    log("media", 23, "FFmpeg instalado localmente", str(local_ffmpeg))


def install_ffmpeg_with_winget_windows() -> bool:
    winget = shutil.which("winget")
    if not winget:
        log("media", 20.5, "Winget nao encontrado", "Baixando FFmpeg pelo metodo portatil")
        return False

    command = [
        winget,
        "install",
        "-e",
        "--id",
        "Gyan.FFmpeg.Essentials",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--silent",
    ]
    log("media", 20.5, "Instalando FFmpeg via winget", " ".join(command))
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        log("media", 21, "Winget nao instalou FFmpeg", compact(result.stdout))
        return False

    refresh_windows_path()
    installed = shutil.which("ffmpeg") or find_ffmpeg_in_common_windows_locations()
    if not installed:
        log("media", 21, "FFmpeg instalado, mas nao encontrado no PATH", "Baixando FFmpeg pelo metodo portatil")
        return False

    add_to_path(Path(installed).parent)
    log("media", 23, "FFmpeg instalado via winget", installed)
    return True


def refresh_windows_path() -> None:
    if platform.system().lower() != "windows":
        return
    try:
        import winreg
    except ImportError:
        return

    paths: list[str] = []
    registry_paths = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for root_key, sub_key in registry_paths:
        try:
            with winreg.OpenKey(root_key, sub_key) as key:
                value, _value_type = winreg.QueryValueEx(key, "Path")
                paths.append(value)
        except OSError:
            continue

    current_path = os.environ.get("PATH", "")
    combined = os.pathsep.join([current_path, *paths])
    os.environ["PATH"] = os.path.expandvars(combined)


def find_ffmpeg_in_common_windows_locations() -> str | None:
    candidates: list[Path] = []
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env_name)
        if value:
            root = Path(value)
            candidates.extend(root.glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/ffmpeg.exe"))
            candidates.extend(root.glob("ffmpeg*/**/ffmpeg.exe"))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def find_local_ffmpeg() -> Path | None:
    expected = LOCAL_FFMPEG_DIR / "bin" / "ffmpeg.exe"
    if expected.exists():
        return expected
    for candidate in LOCAL_FFMPEG_DIR.glob("**/ffmpeg.exe"):
        return candidate
    return None


def download_ffmpeg_windows() -> None:
    LOCAL_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = LOCAL_TOOLS_DIR / "ffmpeg-release-essentials.zip"

    log("media", 20.5, "Baixando FFmpeg para Windows", FFMPEG_URL)
    urllib.request.urlretrieve(FFMPEG_URL, archive_path)

    extract_root = LOCAL_TOOLS_DIR / "ffmpeg-extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    log("media", 21.5, "Extraindo FFmpeg", str(archive_path))
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_root)

    ffmpeg_exe = next(extract_root.glob("**/ffmpeg.exe"), None)
    if not ffmpeg_exe:
        raise RuntimeError("Pacote do FFmpeg extraido, mas ffmpeg.exe nao foi encontrado.")

    if LOCAL_FFMPEG_DIR.exists():
        shutil.rmtree(LOCAL_FFMPEG_DIR)
    shutil.move(str(ffmpeg_exe.parents[1]), str(LOCAL_FFMPEG_DIR))
    archive_path.unlink(missing_ok=True)
    shutil.rmtree(extract_root, ignore_errors=True)


def add_to_path(directory: Path) -> None:
    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []
    directory_text = str(directory)
    if directory_text not in path_entries:
        os.environ["PATH"] = directory_text + os.pathsep + current_path if current_path else directory_text


def ensure_backend_running(python_bin: Path) -> None:
    if http_ok(f"http://{HOST}:{BACKEND_PORT}/health"):
        if http_ok(f"http://{HOST}:{BACKEND_PORT}/app"):
            log("backend", 90, "Backend ja esta rodando", f"http://{HOST}:{BACKEND_PORT}")
            return
        raise RuntimeError(
            f"Ja existe um backend antigo rodando em http://{HOST}:{BACKEND_PORT}, mas ele nao esta servindo o frontend. "
            "Pare esse processo antigo e clique Start app novamente. Exemplo: pkill -f 'uvicorn backend.app.main:app'."
        )

    proc = subprocess.Popen(
        [str(python_bin), "-m", "uvicorn", "backend.app.main:app", "--host", HOST, "--port", str(BACKEND_PORT)],
        cwd=str(ROOT),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    PROCESSES["backend"] = proc
    threading.Thread(target=drain_process_output, args=("backend", proc), daemon=True).start()
    wait_for_http(f"http://{HOST}:{BACKEND_PORT}/health", 45, "Backend nao respondeu em 45s")
    log("backend", 94, "Backend online", f"http://{HOST}:{BACKEND_PORT}")


def drain_process_output(name: str, proc: subprocess.Popen) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        text = compact(line)
        if text:
            append_log(name, f"{name} log", text)


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
