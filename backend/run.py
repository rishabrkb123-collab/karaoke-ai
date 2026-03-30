"""
Start uvicorn on the first free port starting from 8000.
Writes the chosen port to .port so vite.config.js can read it for the proxy.
"""
import socket
import subprocess
import sys
import os


def find_free_port(start: int = 8000) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range 8000-8019")


port = find_free_port()

port_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".port")
with open(port_file, "w") as f:
    f.write(str(port))

print(f"[run.py] Backend port: {port}", flush=True)

subprocess.run([
    sys.executable, "-m", "uvicorn", "main:app",
    "--host", "0.0.0.0",
    f"--port={port}",
    "--reload",
])
