#!/usr/bin/env python3
"""
docencIA Dev Environment Manager
Monorepo (docencIA): PostgreSQL+pgvector (Docker), FastAPI backend (backend/, via uv/uvicorn),
frontend React/Vite (frontend/, via bun).
Usage: python dev.py <command>
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any

# --- Configuration ---
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(WORKSPACE_ROOT, "logs")
STATE_FILE = os.path.join(LOGS_DIR, "dev_state.json")

BACKEND_DIR = os.path.join(WORKSPACE_ROOT, "backend")
FRONTEND_DIR = os.path.join(WORKSPACE_ROOT, "frontend")
COMPOSE_FILE = os.path.join(WORKSPACE_ROOT, "infra", "compose.yml")
ENV_FILE = os.path.join(WORKSPACE_ROOT, ".env")

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
DB_PORT = 5432

COMPOSE_INFRA_SERVICES = ["db"]

# --- ANSI Colors ---
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"


def log_info(msg):
    print(f"{BLUE}[INFO]{RESET} {msg}")


def log_success(msg):
    print(f"{GREEN}[SUCCESS]{RESET} {msg}")


def log_warning(msg):
    print(f"{YELLOW}[WARNING]{RESET} {msg}")


def log_error(msg):
    print(f"{RED}[ERROR]{RESET} {msg}")


# --- Helpers ---


def get_docker_compose_cmd():
    try:
        res = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=False
        )
        if res.returncode == 0:
            return ["docker", "compose"]
    except FileNotFoundError:
        pass
    try:
        res = subprocess.run(
            ["docker-compose", "version"], capture_output=True, check=False
        )
        if res.returncode == 0:
            return ["docker-compose"]
    except FileNotFoundError:
        pass
    return None


def load_state() -> dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return dict(json.load(f))
        except (OSError, ValueError) as e:
            log_warning(f"Failed to load state file, using defaults: {e}")
    return {"backend_pid": None, "frontend_pid": None}


def save_state(state):
    os.makedirs(LOGS_DIR, exist_ok=True)
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        log_error(f"Failed to save state file: {e}")


def get_process_cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "r") as f:
            return f.read().replace("\x00", " ")
    except OSError:
        return ""


def is_backend_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    cmdline = get_process_cmdline(pid)
    return "uvicorn" in cmdline or "uv" in cmdline


def is_frontend_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    cmdline = get_process_cmdline(pid)
    return "bun" in cmdline or "vite" in cmdline


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def load_env_file():
    """Load env vars from .env file into a dict for subprocess."""
    env = os.environ.copy()
    if not os.path.exists(ENV_FILE):
        return env
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env.setdefault(key.strip(), val.strip())
    return env


def backend_env_for_local_run():
    """
    DATABASE_URL no .env aponta pro host "db" (nome do serviço no Compose),
    válido só na rede interna dos containers. Rodando o backend localmente
    (fora do Docker) contra o Postgres publicado em localhost:5432, o host
    precisa virar "localhost" — senão a resolução de nome falha.
    """
    env = load_env_file()
    db_url = env.get("DATABASE_URL")
    if db_url:
        env["DATABASE_URL"] = db_url.replace("@db:", "@localhost:")
    return env


def kill_process_group_robust(pid, name):
    if not pid:
        return
    log_info(f"Stopping {name} (PID group {pid})...")
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.killpg(pid, 0)
            except OSError:
                log_success(f"{name} stopped successfully.")
                return
        log_warning(f"{name} did not stop gracefully. Forcing with SIGKILL...")
        os.killpg(pid, signal.SIGKILL)
        log_success(f"{name} terminated with SIGKILL.")
    except ProcessLookupError:
        log_info(f"{name} was not running.")
    except OSError as e:
        log_error(f"Error stopping {name}: {e}")


def print_last_lines(filepath, n, prefix, color):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f.readlines()[-n:]:
                sys.stdout.write(f"{color}{prefix}{RESET} {line}")
            sys.stdout.flush()
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"Error reading {filepath}: {e}")


def follow_file(filepath, prefix, color):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            while True:
                pos = f.tell()
                try:
                    actual = os.path.getsize(filepath)
                except OSError:
                    actual = 0
                if actual < pos:
                    f.seek(0)
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                sys.stdout.write(f"{color}{prefix}{RESET} {line}")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass


def ensure_frontend_deps() -> bool:
    """Garante bun instalado e frontend/node_modules presente. False = não dá para seguir."""
    if shutil.which("bun") is None:
        log_error(
            "bun não encontrado no PATH. Instale em https://bun.sh para rodar o frontend."
        )
        return False
    if os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        return True
    log_info("frontend/node_modules ausente. Rodando 'bun install'...")
    res = subprocess.run(
        ["bun", "install"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        log_error(f"Falha no 'bun install':\n{res.stderr}")
        return False
    log_success("Dependências do frontend instaladas.")
    return True


def start_frontend(state):
    """Sobe o Vite em background. Não derruba o script em caso de falha: o backend já pode ter subido."""
    if is_frontend_running(state.get("frontend_pid")):
        log_warning("Frontend já está rodando!")
        return
    if is_port_in_use(FRONTEND_PORT):
        log_error(
            f"Porta {FRONTEND_PORT} já está em uso! Não é possível iniciar o frontend."
        )
        return
    if not ensure_frontend_deps():
        return

    log_info("Iniciando frontend (Vite) em background...")
    frontend_log = os.path.join(LOGS_DIR, "frontend.log")
    # O proxy do Vite (/api) aponta para o backend local; --strictPort evita o
    # Vite pular para outra porta e o wait_for_port conferir o processo errado.
    frontend_env = os.environ.copy()
    frontend_env["API_ALVO"] = f"http://localhost:{BACKEND_PORT}"

    with open(frontend_log, "w") as log_file:
        p = subprocess.Popen(
            [
                "bun",
                "run",
                "dev",
                "--host",
                "0.0.0.0",
                "--port",
                str(FRONTEND_PORT),
                "--strictPort",
            ],
            cwd=FRONTEND_DIR,
            env=frontend_env,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        state["frontend_pid"] = p.pid
        log_success(f"Frontend iniciado (PID group: {p.pid}). Logs: logs/frontend.log")
        log_info(f"Aguardando frontend (porta {FRONTEND_PORT}) ficar pronto...")
        if wait_for_port(FRONTEND_PORT, timeout=30):
            log_success(f"Frontend pronto em http://localhost:{FRONTEND_PORT}")
        else:
            log_warning("Frontend não respondeu após 30s. Verifique logs/frontend.log")


# --- Core Commands ---


def start_dev():
    state = load_state()
    b_running = is_backend_running(state.get("backend_pid"))
    f_running = is_frontend_running(state.get("frontend_pid"))

    if b_running and f_running:
        log_warning("Backend e frontend já estão rodando!")
        show_status()
        return

    os.makedirs(LOGS_DIR, exist_ok=True)

    if b_running:
        log_warning("Backend já está rodando! Iniciando só o frontend.")
        start_frontend(state)
        save_state(state)
        show_status()
        return

    # --- 1. Database (Docker Compose: pgvector) ---
    compose_cmd = get_docker_compose_cmd()
    if not compose_cmd:
        log_error("Docker Compose não encontrado. Instale o Docker.")
        sys.exit(1)

    db_running = is_port_in_use(DB_PORT)
    if db_running:
        log_info(f"Porta {DB_PORT} já em uso. Verificando containers docker...")
        res = subprocess.run(
            compose_cmd + ["-f", COMPOSE_FILE, "ps", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "docencia" in res.stdout or "db" in res.stdout:
            log_success("Container do banco já está rodando.")
        else:
            log_warning(f"Porta {DB_PORT} em uso por outro processo.")
    else:
        log_info("Iniciando Postgres+pgvector via Docker Compose...")
        cmd = compose_cmd + ["-f", COMPOSE_FILE, "up", "-d"] + COMPOSE_INFRA_SERVICES
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            log_error(f"Falha ao subir Docker Compose:\n{res.stderr}")
            sys.exit(1)
        log_success("Serviço db (Docker Compose) iniciado.")

        log_info(f"Aguardando banco (porta {DB_PORT}) ficar pronto...")
        if wait_for_port(DB_PORT, timeout=20):
            log_success("Banco pronto.")
        else:
            log_warning(f"Porta {DB_PORT} não abriu após 20s. Prosseguindo...")

    # --- 1b. Migrações (Alembic) ---
    # A porta 5432 abrir antes do Postgres aceitar conexão real: enquanto o
    # container roda o docker-entrypoint-initdb.d, ele derruba conexões.
    # Retry até o servidor ficar pronto, em vez de depender só do TCP check.
    log_info("Aplicando migrações (alembic upgrade head)...")
    migracao = None
    for tentativa in range(1, 11):
        migracao = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=WORKSPACE_ROOT,
            env=backend_env_for_local_run(),
            capture_output=True,
            text=True,
            check=False,
        )
        if migracao.returncode == 0:
            break
        log_info(
            f"Banco ainda não aceitou conexão (tentativa {tentativa}/10). Aguardando..."
        )
        time.sleep(2)
    if migracao is not None and migracao.returncode != 0:
        log_error(f"Falha ao aplicar migrações:\n{migracao.stderr}")
        sys.exit(1)
    log_success("Migrações aplicadas.")

    # --- 2. Backend (FastAPI via uv/uvicorn) ---
    if is_port_in_use(BACKEND_PORT):
        log_error(
            f"Porta {BACKEND_PORT} já está em uso! Não é possível iniciar o backend."
        )
    else:
        log_info("Iniciando backend (FastAPI/uvicorn) em background...")

        backend_log = os.path.join(LOGS_DIR, "backend.log")
        backend_env = backend_env_for_local_run()

        with open(backend_log, "w") as log_file:
            p = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "uvicorn",
                    "backend.app.main:app",
                    "--reload",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(BACKEND_PORT),
                ],
                cwd=WORKSPACE_ROOT,
                env=backend_env,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
            state["backend_pid"] = p.pid
            log_success(
                f"Backend iniciado (PID group: {p.pid}). Logs: logs/backend.log"
            )
            log_info(f"Aguardando backend (porta {BACKEND_PORT}) ficar pronto...")
            if wait_for_port(BACKEND_PORT, timeout=60):
                log_success(f"Backend pronto em http://localhost:{BACKEND_PORT}")
            else:
                log_warning(
                    "Backend não respondeu após 60s. Verifique logs/backend.log"
                )

    # --- 3. Frontend (React/Vite via bun) ---
    start_frontend(state)

    save_state(state)
    log_success("Serviços iniciados!")
    log_info("Logs: python dev.py logs")
    log_info("Status: python dev.py status")
    log_info("Stop: python dev.py stop")


def stop_dev():
    state = load_state()

    if state.get("frontend_pid"):
        kill_process_group_robust(state["frontend_pid"], "frontend")
        state["frontend_pid"] = None

    if state.get("backend_pid"):
        kill_process_group_robust(state["backend_pid"], "backend")
        state["backend_pid"] = None

    compose_cmd = get_docker_compose_cmd()
    if compose_cmd:
        log_info("Parando Docker Compose...")
        cmd = compose_cmd + ["-f", COMPOSE_FILE, "stop"] + COMPOSE_INFRA_SERVICES
        subprocess.run(cmd, capture_output=True, check=False)
        log_success("Docker Compose parado.")

    save_state(state)
    log_success("Todos os serviços de desenvolvimento parados.")


def restart_dev():
    log_info("Reiniciando todos os serviços...")
    stop_dev()
    time.sleep(1.5)
    start_dev()


def build_frontend():
    """Typecheck + bundle de produção do frontend (bun run build → frontend/dist)."""
    if not ensure_frontend_deps():
        sys.exit(1)
    log_info("Buildando frontend (bun run build)...")
    res = subprocess.run(["bun", "run", "build"], cwd=FRONTEND_DIR, check=False)
    if res.returncode != 0:
        log_error("Build do frontend falhou.")
        sys.exit(res.returncode)
    log_success("Build do frontend concluído (frontend/dist).")


def show_status():
    state = load_state()
    b_pid = state.get("backend_pid")
    f_pid = state.get("frontend_pid")

    b_running = is_backend_running(b_pid)
    f_running = is_frontend_running(f_pid)

    print(f"\n{BOLD}docencIA Dev Environment Status:{RESET}")
    print("-" * 60)

    b_status = (
        f"{GREEN}RUNNING{RESET} (PID: {b_pid})" if b_running else f"{RED}STOPPED{RESET}"
    )
    print(f"Backend  (FastAPI {BACKEND_PORT}):     {b_status}")

    f_status = (
        f"{GREEN}RUNNING{RESET} (PID: {f_pid})" if f_running else f"{RED}STOPPED{RESET}"
    )
    print(f"Frontend (Vite {FRONTEND_PORT}):       {f_status}")

    db_status = (
        f"{GREEN}RUNNING{RESET} (Port {DB_PORT})"
        if is_port_in_use(DB_PORT)
        else f"{RED}STOPPED{RESET}"
    )
    print(f"Database (Postgres+pgvector {DB_PORT}): {db_status}")

    print("-" * 60)
    print("Logs:")
    print("  Backend:  logs/backend.log")
    print("  Frontend: logs/frontend.log")
    print()
    print("Commands:")
    print("  python dev.py start    - Inicia banco, backend e frontend")
    print("  python dev.py stop     - Para todos os serviços")
    print("  python dev.py status   - Mostra status atual")
    print("  python dev.py logs     - Stream de logs")
    print()


def stream_logs(service=None):
    if service:
        service = service.lower()
        if service == "backend":
            path = os.path.join(LOGS_DIR, "backend.log")
            prefix = "[backend]"
            color = GREEN
        elif service in ("frontend", "front"):
            path = os.path.join(LOGS_DIR, "frontend.log")
            prefix = "[frontend]"
            color = MAGENTA
        else:
            log_error(f"Serviço desconhecido: {service}. Use 'backend' ou 'frontend'.")
            sys.exit(1)

        if not os.path.exists(path):
            with open(path, "w"):
                pass
        print(f"{CYAN}--- Streaming {service} logs (Ctrl+C para sair) ---{RESET}\n")
        print_last_lines(path, 30, prefix, color)
        try:
            follow_file(path, prefix, color)
        except KeyboardInterrupt:
            print("\nSaindo.")
    else:
        backend_path = os.path.join(LOGS_DIR, "backend.log")
        frontend_path = os.path.join(LOGS_DIR, "frontend.log")
        for path in (backend_path, frontend_path):
            if not os.path.exists(path):
                with open(path, "w"):
                    pass

        print(
            f"{CYAN}--- Streaming logs do backend e do frontend (Ctrl+C para sair) ---{RESET}\n"
        )
        print_last_lines(backend_path, 30, "[backend]", GREEN)
        print_last_lines(frontend_path, 30, "[frontend]", MAGENTA)

        t1 = threading.Thread(
            target=follow_file, args=(backend_path, "[backend]", GREEN), daemon=True
        )
        t2 = threading.Thread(
            target=follow_file, args=(frontend_path, "[frontend]", MAGENTA), daemon=True
        )
        t1.start()
        t2.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nSaindo do stream de logs.")


def clean_dev():
    """Para tudo E destrói o volume do banco."""
    stop_dev()
    compose_cmd = get_docker_compose_cmd()
    if compose_cmd:
        log_info("Limpando volumes Docker...")
        cmd = compose_cmd + ["-f", COMPOSE_FILE, "down", "-v"]
        subprocess.run(cmd, capture_output=True, check=False)
        log_success("Volumes Docker removidos.")

    log_info("Limpando arquivos de log...")
    for file in ["backend.log", "frontend.log", "dev_state.json"]:
        path = os.path.join(LOGS_DIR, file)
        if os.path.exists(path):
            try:
                os.remove(path)
                log_success(f"Removido {file}")
            except OSError as e:
                log_error(f"Falha ao remover {file}: {e}")
    log_success("Limpeza completa. Dados do banco foram destruídos.")


def purge_dev():
    """Remove artefatos de build — mantém o banco intacto."""
    state = load_state()
    b_running = is_backend_running(state.get("backend_pid"))
    f_running = is_frontend_running(state.get("frontend_pid"))

    if b_running or f_running:
        log_info("Parando processos em execução...")
        stop_dev()
        log_info("Processos parados.")

    log_info("Removendo cache do backend (__pycache__)...")
    for root, dirs, _files in os.walk(BACKEND_DIR):
        if "__pycache__" in dirs:
            path = os.path.join(root, "__pycache__")
            shutil.rmtree(path, ignore_errors=True)

    # node_modules fica: reinstalar é lento, e não é artefato de build.
    log_info("Removendo build e cache do frontend (dist, node_modules/.vite)...")
    for path in (
        os.path.join(FRONTEND_DIR, "dist"),
        os.path.join(FRONTEND_DIR, "node_modules", ".vite"),
    ):
        shutil.rmtree(path, ignore_errors=True)

    log_info("Limpando arquivos de log...")
    for file in ["backend.log", "frontend.log", "dev_state.json"]:
        path = os.path.join(LOGS_DIR, file)
        if os.path.exists(path):
            try:
                os.remove(path)
                log_success(f"Removido {file}")
            except OSError as e:
                log_error(f"Falha ao remover {file}: {e}")

    log_success("Purge completo. Dados do banco preservados.")


def print_help():
    print(f"""
{BOLD}docencIA Dev Environment Manager{RESET}

{BOLD}Uso:{RESET} python dev.py <command>

{BOLD}Commands:{RESET}
  {GREEN}start{RESET}         Inicia banco (Postgres+pgvector), backend (FastAPI/uvicorn --reload)
                e frontend (Vite, porta {FRONTEND_PORT}; roda 'bun install' se faltar node_modules).
  {RED}stop{RESET}          Para frontend, backend e containers docker.
  {YELLOW}restart{RESET}       Para e inicia tudo de novo.
  {CYAN}status{RESET}        Verifica status dos processos e portas.
  {BLUE}logs{RESET}          Stream de logs em tempo real (backend e frontend).
  {BLUE}logs backend{RESET}    Stream só do backend.
  {BLUE}logs frontend{RESET}   Stream só do frontend.
  {RED}clean{RESET}         Para tudo, remove logs E destrói o volume do banco.
  {MAGENTA}purge{RESET}        Remove artefatos de build/cache (mantém o banco).
  {MAGENTA}build{RESET}         Typecheck + bundle de produção do frontend (frontend/dist).
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "start":
        start_dev()
    elif cmd == "stop":
        stop_dev()
    elif cmd == "restart":
        restart_dev()
    elif cmd == "build":
        build_frontend()
    elif cmd == "status":
        show_status()
    elif cmd in ("log", "logs"):
        srv = sys.argv[2] if len(sys.argv) > 2 else None
        stream_logs(srv)
    elif cmd == "clean":
        clean_dev()
    elif cmd == "purge":
        purge_dev()
    else:
        log_error(f"Comando desconhecido: {cmd}")
        print_help()
        sys.exit(1)
