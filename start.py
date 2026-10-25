"""Set up and run Kurippu and its optional live WhatsApp bridge."""
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT / "wa-bridge"
TOKEN_FILE = ROOT / "data" / "whatsapp.token"


def fail(message):
    print(f"\nSetup error: {message}", file=sys.stderr)
    raise SystemExit(1)


def configured_port(name, default):
    try:
        port = int(os.environ.get(name, default))
    except ValueError:
        fail(f"{name} must be a TCP port number.")
    if not 1 <= port <= 65535:
        fail(f"{name} must be between 1 and 65535.")
    return port


APP_PORT = configured_port("KURIPPU_PORT", "8765")
BRIDGE_PORT = configured_port("WA_BRIDGE_PORT", "8766")
URL = f"http://127.0.0.1:{APP_PORT}"


def python_in_venv():
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_python_environment():
    if sys.version_info < (3, 10):
        fail("Python 3.10 or newer is required. Install Python, then run this launcher again.")
    python = python_in_venv()
    if not python.exists():
        print("First-time setup: creating the Kurippu Python environment…", flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
            print("Installing Kurippu…", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT)], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            fail(f"Could not install Kurippu ({error}). Check your internet connection and try again.")
    return python


def ensure_node():
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        fail("Node.js 18 or newer is required for live WhatsApp. Install Node.js, then try again.")
    try:
        version = subprocess.run([node, "--version"], check=True, capture_output=True,
                                 text=True).stdout.strip().lstrip("v")
        major = int(version.split(".", 1)[0])
    except (subprocess.CalledProcessError, ValueError, IndexError):
        fail("Could not read the Node.js version. Reinstall Node.js and try again.")
    if major < 18:
        fail(f"Node.js 18 or newer is required; this computer has Node.js {version}.")
    if not (BRIDGE / "node_modules" / "whatsapp-web.js").is_dir():
        print("First-time setup: installing the WhatsApp connection…", flush=True)
        try:
            subprocess.run([npm, "install", "--prefix", str(BRIDGE)], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            fail(f"Could not install the WhatsApp connection ({error}). Check your internet connection and try again.")
    return node


def ensure_token():
    token = os.environ.get("KURIPPU_WA_TOKEN", "").strip()
    if token:
        return token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        descriptor = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
            token_file.write(token)
            token_file.write("\n")
    if not token:
        fail(f"The WhatsApp token file is empty: {TOKEN_FILE}")
    return token


def ensure_port_available(port, name):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            fail(f"Port {port} is already in use, so {name} cannot start. Close the other app and try again.")


def wait_for_server(process, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail("Kurippu stopped during startup. Review the error shown above.")
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    fail("Kurippu did not start in time. Check the error shown above, then try again.")


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    os.chdir(ROOT)
    ensure_port_available(APP_PORT, "Kurippu")
    ensure_port_available(BRIDGE_PORT, "WhatsApp")
    python = ensure_python_environment()
    node = ensure_node()
    token = ensure_token()
    environment = os.environ.copy()
    environment["KURIPPU_WA_TOKEN"] = token
    environment["KURIPPU_URL"] = URL

    server = bridge = None
    try:
        print("\nStarting Kurippu…", flush=True)
        server = subprocess.Popen([str(python), "-m", "kurippu"], cwd=ROOT, env=environment)
        wait_for_server(server)
        print("Starting the WhatsApp connection…", flush=True)
        bridge = subprocess.Popen([node, "index.js"], cwd=BRIDGE, env=environment)
        print(f"\nKurippu is ready at {URL}", flush=True)
        print("Open the WhatsApp page in Kurippu and scan the QR code to link the shop phone.")
        print("Keep this window open. Press Ctrl+C here to stop Kurippu and WhatsApp.\n", flush=True)
        webbrowser.open(URL)
        while True:
            if server.poll() is not None:
                print("\nKurippu stopped.", flush=True)
                break
            if bridge.poll() is not None:
                print("\nThe WhatsApp connection stopped. On Linux, if the error says “No usable sandbox”, see the Linux troubleshooting note in README.", flush=True)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping Kurippu…", flush=True)
    except subprocess.CalledProcessError as error:
        fail(f"Automatic setup did not finish (exit code {error.returncode}). Check your internet connection and try again.")
    finally:
        stop_process(bridge)
        stop_process(server)


if __name__ == "__main__":
    main()
