import os
import signal
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

ALLOW_HOSTS = {
    "registry.npmjs.org",
    "registry.yarnpkg.com",
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
}
_proxy_lock = threading.Lock()
_proxy_port: int | None = None


def host_allowed(host: str) -> bool:
    name = host.split(":")[0].lower().rstrip(".")
    if name in ALLOW_HOSTS:
        return True
    return name.endswith(".npmjs.org") or name.endswith(".github.com") or name.endswith(".githubusercontent.com")


class _Proxy(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data += chunk
        line = data.split(b"\r\n", 1)[0].decode(errors="replace")
        parts = line.split(" ")
        target = parts[1] if len(parts) > 1 else ""
        if not host_allowed(target):
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        if parts[0] != "CONNECT":
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        host, _, port = target.partition(":")
        try:
            upstream = socket.create_connection((host, int(port or "443")), timeout=10)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        self.request.setblocking(False)
        upstream.setblocking(False)
        sockets = [self.request, upstream]
        while sockets:
            readable, _, _ = __import__("select").select(sockets, [], [], 10)
            if not readable:
                break
            for sock in readable:
                try:
                    chunk = sock.recv(65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    sockets = []
                    break
                other = upstream if sock is self.request else self.request
                other.sendall(chunk)
        upstream.close()


def ensure_proxy() -> int:
    global _proxy_port
    with _proxy_lock:
        if _proxy_port:
            return _proxy_port
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Proxy)
        server.daemon_threads = True
        _proxy_port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return _proxy_port


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


def run_command(folder: Path, command: str, should_stop, timeout: float = 120) -> tuple[int, str]:
    limit = min(600, max(0.1, float(timeout)))
    if not local_mode():
        return _docker(folder, command, should_stop, limit)
    if not command_stays_inside(folder, command):
        raise PermissionError(command)
    process = subprocess.Popen(
        command,
        cwd=folder,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        env={**os.environ, "CI": "1", "DEBIAN_FRONTEND": "noninteractive"},
    )
    started = time.time()
    while process.poll() is None:
        if should_stop():
            _kill(process)
            return 1, "stopped"
        if time.time() - started > limit:
            _kill(process)
            return 1, "timed out"
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
    return process.returncode or 0, (process.stdout.read() if process.stdout else "")


def _kill(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()


def _docker(folder: Path, command: str, should_stop, timeout: float) -> tuple[int, str]:
    import docker

    client = docker.from_env()
    proxy_ip = _docker_proxy(client)
    container = client.containers.run(
        "node:22-bookworm",
        ["sh", "-c", command],
        volumes={str(folder.resolve()): {"bind": "/workspace", "mode": "rw"}},
        working_dir="/workspace",
        detach=True,
        user=f"{os.getuid()}:{os.getgid()}",
        network="atelier-internal",
        environment={
            "HTTP_PROXY": f"http://{proxy_ip}:8080",
            "HTTPS_PROXY": f"http://{proxy_ip}:8080",
            "http_proxy": f"http://{proxy_ip}:8080",
            "https_proxy": f"http://{proxy_ip}:8080",
            "PROXY_HOST": proxy_ip,
            "CI": "1",
            "DEBIAN_FRONTEND": "noninteractive",
        },
    )
    started = time.time()
    while container.status != "exited":
        container.reload()
        if should_stop() or time.time() - started > timeout:
            container.kill()
            container.remove()
            return 1, "timed out" if time.time() - started > timeout else "stopped"
    logs = container.logs().decode()
    code = container.wait().get("StatusCode", 1)
    container.remove()
    return code, logs


_NODE_PROXY = """
const net = require('net');
const http = require('http');
const allow = ['registry.npmjs.org','registry.yarnpkg.com','github.com','api.github.com','codeload.github.com','objects.githubusercontent.com','pypi.org','files.pythonhosted.org'];
function ok(host) {
  const name = String(host || '').split(':')[0].toLowerCase();
  return allow.includes(name) || name.endsWith('.npmjs.org') || name.endsWith('.github.com') || name.endsWith('.githubusercontent.com');
}
const server = http.createServer((req, res) => { res.writeHead(403); res.end(); });
server.on('connect', (req, socket) => {
  if (!ok(req.url)) { socket.write('HTTP/1.1 403 Forbidden\\r\\n\\r\\n'); socket.end(); return; }
  const parts = String(req.url).split(':');
  const upstream = net.connect(Number(parts[1] || 443), parts[0], () => {
    socket.write('HTTP/1.1 200 Connection Established\\r\\n\\r\\n');
    upstream.pipe(socket); socket.pipe(upstream);
  });
  upstream.on('error', () => socket.end());
});
server.listen(8080, '0.0.0.0');
"""


def _docker_proxy(client):
    try:
        network = client.networks.get("atelier-internal")
    except Exception:
        network = client.networks.create("atelier-internal", internal=True)
    try:
        proxy = client.containers.get("atelier-proxy")
        if proxy.status != "running":
            proxy.start()
    except Exception:
        proxy = client.containers.run("node:22-bookworm", ["node", "-e", _NODE_PROXY], name="atelier-proxy", detach=True)
    proxy.reload()
    attached = proxy.attrs["NetworkSettings"]["Networks"]
    if "atelier-internal" not in attached:
        network.connect(proxy)
        proxy.reload()
        attached = proxy.attrs["NetworkSettings"]["Networks"]
    return attached["atelier-internal"]["IPAddress"]
