import base64
import json
import os
import platform
import re
import socket
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).with_name("collect.ps1")
IS_WINDOWS = platform.system() == "Windows"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args, timeout):
    return subprocess.run(
        args,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        creationflags=NO_WINDOW,
    )


def _clean(value):
    if isinstance(value, list):
        return [_clean(v) for v in value if v is not None]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def run_powershell(days=7, timeout=120):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "datos.json"
        path = str(out).replace("'", "''")
        script = f"$Days = {int(days)}\n$OutFile = '{path}'\n" + SCRIPT.read_text(encoding="utf-8")
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        exe = "powershell.exe" if IS_WINDOWS else "pwsh"
        proc = _run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded], timeout)
        if not out.exists():
            detail = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"PowerShell no devolvió datos. {detail}".strip())
        return _clean(json.loads(out.read_text(encoding="utf-8-sig")))


def ping(host, timeout_ms=1500):
    if not host:
        return None
    count = "-n" if IS_WINDOWS else "-c"
    wait = ["-w", str(timeout_ms)] if IS_WINDOWS else ["-W", str(max(1, timeout_ms // 1000))]
    start = time.perf_counter()
    try:
        proc = _run(["ping", count, "1", *wait, host], timeout=timeout_ms / 1000 + 3)
    except (OSError, subprocess.TimeoutExpired):
        return {"host": host, "ok": False, "ms": None}
    text = proc.stdout.decode("utf-8", "replace")
    ok = proc.returncode == 0 and "TTL=" in text.upper()
    match = re.search(r"[=<](\d+(?:[.,]\d+)?)\s*ms", text)
    ms = float(match.group(1).replace(",", ".")) if match else round((time.perf_counter() - start) * 1000)
    return {"host": host, "ok": ok, "ms": ms if ok else None}


def resolve(name="www.microsoft.com"):
    start = time.perf_counter()
    try:
        ip = socket.gethostbyname(name)
        return {"host": name, "ok": True, "ip": ip, "ms": round((time.perf_counter() - start) * 1000)}
    except OSError:
        return {"host": name, "ok": False, "ip": None, "ms": None}


def http_check(url="http://www.msftconnecttest.com/connecttest.txt", timeout=6):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ok = resp.status == 200
        return {"url": url, "ok": ok, "ms": round((time.perf_counter() - start) * 1000)}
    except Exception:
        return {"url": url, "ok": False, "ms": None}


def wifi():
    if not IS_WINDOWS:
        return None
    try:
        proc = _run(["netsh", "wlan", "show", "interfaces"], timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = proc.stdout.decode("cp850", "replace")
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", text, re.M)
    signal = re.search(r"^\s*(?:Signal|Se\S{1,2}al)\s*:\s*(\d+)\s*%", text, re.M)
    if not ssid:
        return None
    return {"ssid": ssid.group(1).strip(), "signal": int(signal.group(1)) if signal else None}


def connectivity(network):
    gateway = next((g for n in network for g in n.get("gateway", [])), None)
    return {
        "gateway": ping(gateway),
        "internet": ping("1.1.1.1"),
        "dns": resolve(),
        "http": http_check(),
        "wifi": wifi(),
    }


def collect(days=7, progress=lambda _msg: None):
    progress("Recogiendo datos del sistema…")
    data = run_powershell(days)
    progress("Comprobando la conexión…")
    data["connectivity"] = connectivity(data.get("network") or [])
    data["collectedAt"] = datetime.now().replace(microsecond=0).isoformat()
    data["eventDays"] = days
    data.setdefault("system", None)
    if data["system"] is None:
        data["system"] = {"computer": os.environ.get("COMPUTERNAME") or platform.node()}
    return data


def load_demo():
    path = Path(__file__).with_name("demo.json")
    return json.loads(path.read_text(encoding="utf-8"))
