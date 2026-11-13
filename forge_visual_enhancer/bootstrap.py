"""Prepare a separately obtained Visual Enhancer for a Forge extension install.

The extension never redistributes Visual Enhancer. A first-time installation
downloads the original release directly from the vendor and checks its digest.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / ".setup"
STATUS = SETUP / "status.json"
CONFIG = ROOT / "config.json"
RUNTIME = ROOT / "runtime" / "Visual-Enhancer"
RELEASE_URL = "https://github.com/Merserk/dlss5-visual-enhancer/releases/download/v20.0/Visual.Enhancer.v20.0.7Zip-Ultra.zip"
RELEASE_SHA256 = "80848974451d99222130b1a527f7836e8cfd098cc7f30a9a0924298445717fae"
RELEASE_BYTES = 903_957_596
CLI_SHA256 = "c5755175d09c6caa607f6286fe5f38fc9bc67bc4c1acf7b66750cbafcee9ec81"
MAX_ARCHIVE_BYTES = 950 * 1024 * 1024
MAX_EXTRACTED_BYTES = 12 * 1024 * 1024 * 1024
MAX_FILES = 30_000


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".status-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.isfile(temp):
            os.unlink(temp)


def _status(phase: str, message: str, percent: int | None = None) -> None:
    data = {"phase": phase, "message": message, "updated": time.time()}
    if percent is not None:
        data["percent"] = max(0, min(100, int(percent)))
    _atomic_json(STATUS, data)


def _complete_cli(path: Path) -> bool:
    return path.name.lower() == "ve_cli.exe" and path.is_file() and (path.parent / "Visual Enhancer.exe").is_file()


def _configured_cli() -> Path | None:
    explicit = os.environ.get("VISUAL_ENHANCER_EXE", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not _complete_cli(path):
            raise RuntimeError("VISUAL_ENHANCER_EXE does not point to a complete Visual Enhancer installation.")
        return path.resolve()
    if CONFIG.is_file():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            path = Path(data["visual_enhancer_exe"]).expanduser()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("The existing Visual Enhancer configuration is invalid; it was not overwritten.") from exc
        if not _complete_cli(path):
            raise RuntimeError("The configured Visual Enhancer program is missing; its settings were not overwritten.")
        return path.resolve()
    runtime_cli = RUNTIME / "VE_CLI.exe"
    if _complete_cli(runtime_cli):
        return runtime_cli.resolve()
    return None


def _find_existing_cli() -> Path | None:
    user = Path.home()
    candidates = [user / "Documents" / "Visual Enhancer" / "VE_CLI.exe",
                  user / "Downloads" / "Visual-Enhancer" / "VE_CLI.exe"]
    for variable in ("LOCALAPPDATA", "PROGRAMFILES"):
        if os.environ.get(variable):
            candidates.extend([Path(os.environ[variable]) / "Programs" / "Visual Enhancer" / "VE_CLI.exe",
                               Path(os.environ[variable]) / "Visual Enhancer" / "VE_CLI.exe"])
    for path in candidates:
        if _complete_cli(path):
            return path.resolve()
    return None


def _record_existing(path: Path) -> None:
    # A user's existing configuration always wins over discovery.
    if not CONFIG.exists():
        _atomic_json(CONFIG, {"visual_enhancer_exe": str(path)})


@contextlib.contextmanager
def _setup_lock():
    SETUP.mkdir(parents=True, exist_ok=True)
    with (SETUP / "setup.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, BlockingIOError):
            pass
        try:
            yield acquired
        finally:
            if acquired:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _download(target: Path, url: str = RELEASE_URL, expected: str = RELEASE_SHA256) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Forge-Visual-Enhancer/1.0"})
    total = 0
    digest = hashlib.sha256()
    last_report = 0.0
    _status("downloading", "Downloading the official Visual Enhancer v20.0 release.", 0)
    with urllib.request.urlopen(request, timeout=45) as response, target.open("xb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ARCHIVE_BYTES:
                raise RuntimeError("The download exceeded the expected size.")
            digest.update(chunk)
            output.write(chunk)
            now = time.monotonic()
            if now - last_report >= 2:
                _status("downloading", "Downloading the official Visual Enhancer v20.0 release.", min(99, total * 100 // RELEASE_BYTES))
                last_report = now
        output.flush()
        os.fsync(output.fileno())
    if digest.hexdigest().lower() != expected.lower():
        raise RuntimeError("The official download failed its SHA-256 integrity check.")


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_FILES or sum(item.file_size for item in entries) > MAX_EXTRACTED_BYTES:
            raise RuntimeError("The release archive is unexpectedly large.")
        for index, item in enumerate(entries):
            name = item.filename
            relative = PurePosixPath(name)
            if (not name or "\\" in name or ":" in name or relative.is_absolute()
                    or ".." in relative.parts or stat.S_ISLNK(item.external_attr >> 16)):
                raise RuntimeError("The release archive contains an unsafe path.")
            target = root.joinpath(*relative.parts)
            if os.path.commonpath((str(root), str(target.resolve()))) != str(root):
                raise RuntimeError("The release archive contains an unsafe path.")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as input_file, target.open("xb") as output:
                    shutil.copyfileobj(input_file, output, length=1024 * 1024)
            if index % 25 == 0:
                _status("extracting", "Preparing Visual Enhancer files.", index * 100 // max(1, len(entries)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worker() -> None:
    with _setup_lock() as acquired:
        if not acquired:
            return
        try:
            cli = _configured_cli()
            if cli is None:
                cli = _find_existing_cli()
                if cli is not None:
                    _record_existing(cli)
            if cli is not None:
                note = "Visual Enhancer is ready."
                if _sha256(cli) != CLI_SHA256:
                    note += " This installed version differs from the tested v20.0 release."
                _status("ready", note, 100)
                return
            if os.name != "nt":
                raise RuntimeError("Automatic setup currently supports Windows; the Visual Enhancer release requires Windows.")
            if RUNTIME.exists():
                raise RuntimeError("The runtime folder already exists but is incomplete; it was not overwritten.")
            SETUP.mkdir(parents=True, exist_ok=True)
            # A private, uniquely named staging directory is the only location
            # removed on completion or failure. Existing app files are untouched.
            with tempfile.TemporaryDirectory(prefix="stage-", dir=SETUP) as temp:
                temp_root = Path(temp)
                archive = temp_root / "official.zip"
                extracted = temp_root / "app"
                _download(archive)
                _status("verifying", "Verified the official download. Preparing the application.", 100)
                _extract(archive, extracted)
                if not _complete_cli(extracted / "VE_CLI.exe") or _sha256(extracted / "VE_CLI.exe") != CLI_SHA256:
                    raise RuntimeError("The official release is incomplete or does not match the tested version.")
                RUNTIME.parent.mkdir(parents=True, exist_ok=True)
                if RUNTIME.exists():
                    raise RuntimeError("A runtime appeared during setup; it was not overwritten.")
                os.rename(extracted, RUNTIME)
            _status("ready", "Visual Enhancer v20.0 is installed and ready.", 100)
        except Exception as exc:
            _status("error", "Setup could not finish: " + str(exc)[:400])
            print("[Forge Visual Enhancer] Setup error:", str(exc), flush=True)


def setup_message() -> str:
    try:
        data = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.is_file() else {}
        if _configured_cli() is not None:
            message = str(data.get("message", "Visual Enhancer is ready.")) if data.get("phase") == "ready" else "Visual Enhancer is ready."
            return "**Setup:** " + message[:500]
        message = str(data.get("message", "Setup has not started."))[:500]
        phase = data.get("phase")
        if phase in {"downloading", "extracting", "verifying", "starting"} and time.time() - float(data.get("updated", 0)) > 900:
            return "**Setup stopped before finishing.** Use Retry setup."
        progress = f" {int(data['percent'])}%" if isinstance(data.get("percent"), int) and phase in {"downloading", "extracting"} else ""
        return f"**Setup:** {message}{progress}"
    except Exception as exc:
        return "**Setup needs attention:** " + str(exc)[:400]


def start_setup() -> str:
    """Return promptly: Forge's extension install request must not wait for 900 MB."""
    try:
        cli = _configured_cli()
        if cli is not None:
            message = "Visual Enhancer is ready."
            if _sha256(cli) != CLI_SHA256:
                message += " This installed version differs from the tested v20.0 release."
            _status("ready", message, 100)
            return setup_message()
        SETUP.mkdir(parents=True, exist_ok=True)
        _status("starting", "Preparing the official Visual Enhancer installation.")
        log_path = SETUP / "install.log"
        with log_path.open("ab") as log:
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen([sys.executable, str(ROOT / "install.py"), "--worker"], cwd=str(ROOT),
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True,
                             creationflags=flags, start_new_session=os.name != "nt")
        return setup_message()
    except Exception as exc:
        try:
            _status("error", "Setup could not start: " + str(exc)[:400])
        except OSError:
            pass
        return "**Setup needs attention:** " + str(exc)[:400]
