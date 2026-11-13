"""Exercise Forge's install hook in a disposable checkout without GPU work."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="forge-ve-hook-check-") as temporary:
    root = Path(temporary)
    checkout = root / "extension"
    shutil.copytree(source, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__", ".setup", "runtime", "config.json"))
    profile = root / "profile"
    app = profile / "Documents" / "Visual Enhancer"
    app.mkdir(parents=True)
    (app / "VE_CLI.exe").write_bytes(b"fake cli for setup test")
    (app / "Visual Enhancer.exe").write_bytes(b"fake gui for setup test")
    environment = os.environ.copy()
    environment.pop("VISUAL_ENHANCER_EXE", None)
    environment["USERPROFILE"] = str(profile)
    environment["HOME"] = str(profile)
    environment["LOCALAPPDATA"] = str(profile / "Local")
    environment["PROGRAMFILES"] = str(profile / "Programs")
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(checkout / "install.py")], cwd=checkout,
                            env=environment, capture_output=True, text=True, timeout=10, check=True)
    assert time.monotonic() - started < 10, "Forge hook did not return promptly"
    status_path = checkout / ".setup" / "status.json"
    status = {}
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if status_path.is_file():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("phase") in {"ready", "error"}:
                break
        time.sleep(.2)
    assert status.get("phase") == "ready", status
    config = json.loads((checkout / "config.json").read_text(encoding="utf-8"))
    assert Path(config["visual_enhancer_exe"]) == app / "VE_CLI.exe"
    assert (app / "VE_CLI.exe").read_bytes() == b"fake cli for setup test"
    shader_root = checkout / "runtime" / "reshade-standard"
    assert len(list((shader_root / "Shaders").glob("*.fx"))) == 5
    assert (shader_root / "Textures").is_dir()
    print("PASS Forge hook returned promptly, reused the app, and installed the official shaders")
