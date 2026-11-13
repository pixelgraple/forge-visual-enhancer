"""Download and verify a clean Windows install without touching a live Forge.

Use Forge's Python interpreter. Downloads about 904 MB; does not render images.
Failed/in-progress test folders are kept for diagnosis rather than deleted
under a possibly running installer.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    if os.name != "nt":
        raise SystemExit("The official Visual Enhancer release requires Windows.")
    source = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(source))
    from forge_visual_enhancer import bootstrap

    root = Path(tempfile.mkdtemp(prefix="forge-ve-fresh-check-"))
    passed = False
    try:
        checkout = root / "extension"
        shutil.copytree(source, checkout, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".setup", "runtime", "config.json", ".venv"))
        profile = root / "empty-profile"
        profile.mkdir()
        env = os.environ.copy()
        env.pop("VISUAL_ENHANCER_EXE", None)
        env.update(USERPROFILE=str(profile), HOME=str(profile),
                   LOCALAPPDATA=str(profile / "Local"), PROGRAMFILES=str(profile / "Programs"))
        env["HOMEDRIVE"], env["HOMEPATH"] = os.path.splitdrive(str(profile))
        command = [sys.executable, str(checkout / "install.py")]
        started = time.monotonic()
        subprocess.run(command, cwd=checkout, env=env, check=True, capture_output=True,
                       text=True, timeout=15)
        print(f"Forge install hook returned in {time.monotonic() - started:.1f}s", flush=True)
        status_path = checkout / ".setup" / "status.json"
        deadline = time.monotonic() + 1800
        previous = None
        status = {}
        while time.monotonic() < deadline:
            if status_path.is_file():
                status = json.loads(status_path.read_text(encoding="utf-8"))
                current = (status.get("phase"), status.get("percent"), status.get("message"))
                if current != previous:
                    print(f"{current[0]}: {current[2]} ({current[1]}%)", flush=True)
                    previous = current
                if status.get("phase") in {"ready", "error"}:
                    break
            time.sleep(1)
        assert status.get("phase") == "ready", status or "No terminal setup status within 30 minutes"
        app = checkout / "runtime" / "Visual-Enhancer"
        cli = app / "VE_CLI.exe"
        assert bootstrap._complete_cli(cli), "The fresh runtime is incomplete"
        assert hashlib.sha256(cli.read_bytes()).hexdigest() == bootstrap.CLI_SHA256
        assert bootstrap.shader_pack_ready(checkout / "runtime" / "reshade-standard")
        assert not (checkout / "config.json").exists(), "Setup reused an external app instead of downloading"
        result = subprocess.run([str(cli), "--help"], cwd=app, capture_output=True, timeout=30)
        assert result.returncode == 0 and b"Visual Enhancer" in result.stdout, "CLI startup failed"
        before = {str(p.relative_to(checkout)): (p.stat().st_size, p.stat().st_mtime_ns)
                  for p in (checkout / "runtime").rglob("*") if p.is_file()}
        subprocess.run(command, cwd=checkout, env=env, check=True, capture_output=True, timeout=15)
        assert json.loads(status_path.read_text(encoding="utf-8"))["phase"] == "ready"
        after = {str(p.relative_to(checkout)): (p.stat().st_size, p.stat().st_mtime_ns)
                 for p in (checkout / "runtime").rglob("*") if p.is_file()}
        assert before == after, "Repeat setup changed the completed runtime"
        passed = True
        print("PASS fresh official download, verified install, shaders, CLI startup, and repeat setup", flush=True)
    finally:
        if passed:
            # Only this exact newly created test directory is disposable.
            if root.parent.resolve() != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("forge-ve-fresh-check-"):
                raise RuntimeError("Unexpected test cleanup path")
            shutil.rmtree(root)
        else:
            print(f"Test folder retained for diagnosis: {root}", flush=True)


if __name__ == "__main__":
    main()
