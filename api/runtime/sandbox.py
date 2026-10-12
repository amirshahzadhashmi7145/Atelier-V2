import os
import subprocess
from pathlib import Path


def local_mode() -> bool:
    if os.environ.get("FORCE_LOCAL") == "1":
        return True
    try:
        import docker

        docker.from_env().ping()
        return False
    except Exception:
        return True


def guard_path(folder: Path, target: str) -> Path:
    resolved = (folder / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
    root = folder.resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionError(target)
    return resolved


def command_stays_inside(folder: Path, command: str) -> bool:
    # ponytail: absolute paths and '..' are refused; this is not a syscall sandbox
    if ".." in command:
        return False
    for token in command.split():
        if token.startswith("/") and not _inside(folder, token):
            return False
    return True


def _inside(folder: Path, target: str) -> bool:
    try:
        guard_path(folder, target)
        return True
    except PermissionError:
        return False


def run_command(folder: Path, command: str, should_stop) -> tuple[int, str]:
    if not local_mode():
        return _docker(folder, command, should_stop)
    if not command_stays_inside(folder, command):
        raise PermissionError(command)
    process = subprocess.Popen(
        command,
        cwd=folder,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while process.poll() is None:
        if should_stop():
            process.kill()
            return 1, "stopped"
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
    return process.returncode or 0, (process.stdout.read() if process.stdout else "")


def _docker(folder: Path, command: str, should_stop) -> tuple[int, str]:
    import docker

    # ponytail: the container is unprivileged and mounts only the project; a domain allow-list needs a proxy
    client = docker.from_env()
    container = client.containers.run(
        "node:22-bookworm",
        ["sh", "-c", command],
        volumes={str(folder.resolve()): {"bind": "/workspace", "mode": "rw"}},
        working_dir="/workspace",
        detach=True,
        user=f"{os.getuid()}:{os.getgid()}",
        network_mode="bridge",
    )
    while container.status != "exited":
        container.reload()
        if should_stop():
            container.kill()
            break
    logs = container.logs().decode()
    code = container.wait().get("StatusCode", 1)
    container.remove()
    return code, logs
