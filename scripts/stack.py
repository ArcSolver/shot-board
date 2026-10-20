"""Run existing ComfyUI plus the local SDK proxy without modifying either."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfy-dir", default=os.environ.get("COMFYUI_DIR", "../vendor/ComfyUI"))
    parser.add_argument("--comfy-python", default=os.environ.get("COMFYUI_PYTHON", "../local/venv/bin/python"))
    parser.add_argument("--log-dir", default=os.environ.get("SHOTBOARD_LOG_DIR", ".runtime/logs"))
    args = parser.parse_args()
    comfy = Path(args.comfy_dir).resolve()
    # Keep the venv executable path: resolving its symlink loses site-packages.
    python = Path(os.path.abspath(args.comfy_python))
    proxy = Path(sys.executable).parent / "comfy-api-proxy"
    if not (comfy / "main.py").is_file() or not python.is_file() or not proxy.is_file():
        parser.error("Set --comfy-dir and --comfy-python to an installed ComfyUI, and install requirements first.")
    for port in (8188, 8189):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                parser.error(f"Port {port} is occupied. Use the existing stack; this launcher owns no existing process.")
    runtime = ROOT / ".runtime"
    for directory in ("input", "output", "user", "temp", "proxy", "cache"):
        (runtime / directory).mkdir(parents=True, exist_ok=True)
    logs = Path(args.log_dir).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    config = runtime / "model-paths.yaml"
    config.write_text("shotboard:\n  base_path: models\n  checkpoints: checkpoints/\n")
    env = os.environ.copy()
    for key in ("COMFY_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", NO_PROXY="127.0.0.1,localhost",
               PYTORCH_ENABLE_MPS_FALLBACK="1", XDG_CACHE_HOME=str(runtime / "cache"))
    commands = [
        [str(python), str(comfy / "main.py"), "--listen", "127.0.0.1", "--port", "8188",
         "--extra-model-paths-config", str(config), "--input-directory", str(runtime / "input"),
         "--output-directory", str(runtime / "output"), "--user-directory", str(runtime / "user"),
         "--temp-directory", str(runtime / "temp"), "--offline", "--disable-partner-nodes",
         "--disable-auto-launch", "--preview-method", "none", "--cache-none", "--reserve-vram", "12", "--fast-disk"],
        [str(proxy), "run", "--host", "127.0.0.1", "--port", "8189", "--comfyui", "http://127.0.0.1:8188",
         "--state-dir", str(runtime / "proxy")],
    ]
    processes = []
    handles = []
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        for name, command in zip(("comfyui", "proxy"), commands):
            handle = (logs / f"{name}.log").open("a")
            handles.append(handle)
            # macOS also enforces loopback-only networking during local generation.
            if sys.platform == "darwin":
                command = ["/usr/bin/sandbox-exec", "-f", str(ROOT / "scripts/loopback.sb"), *command]
            processes.append(subprocess.Popen(command, cwd=comfy, env=env, stdout=handle, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Local engine exited; inspect the runtime logs")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=2):
                    pass
                with socket.create_connection(("127.0.0.1", 8189), timeout=2):
                    pass
                print("READY · ComfyUI :8188 → SDK proxy :8189 · Ctrl-C stops both", flush=True)
                break
            except OSError:
                time.sleep(1)
        else:
            raise TimeoutError("Local stack startup timed out")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()
        print("STOPPED · owned local engine processes", flush=True)


if __name__ == "__main__":
    main()
