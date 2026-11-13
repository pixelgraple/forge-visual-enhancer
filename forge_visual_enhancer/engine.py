"""Run the official Visual Enhancer CLI on one Forge image, without shell commands."""
from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from PIL import Image
from . import bootstrap

ROOT = Path(__file__).resolve().parent.parent
PRESET_FORMAT = "dlss5-visual-enhancer-settings-preset"
STAGES = ["neural_model", "scale_method", "dlss_super_resolution",
          "dlss_ray_reconstruction", "super_resolution", "visionnext", "reshade",
          "coloring", "cas_sharpening", "grain"]
MAX_PRESET_BYTES = 2 * 1024 * 1024


def find_executable():
    """A local installer config or a deliberately set environment variable only."""
    location = os.environ.get("VISUAL_ENHANCER_EXE", "")
    config = ROOT / "config.json"
    if not location and config.is_file():
        try:
            location = json.loads(config.read_text(encoding="utf-8-sig"))["visual_enhancer_exe"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("The Visual Enhancer installation settings are invalid; check the extension setup status.") from exc
    if not location:
        location = str(ROOT / "runtime" / "Visual-Enhancer" / "VE_CLI.exe")
    path = Path(location).expanduser()
    if not path.is_file() or path.name.lower() != "ve_cli.exe":
        raise RuntimeError("Visual Enhancer is not ready yet. Check the extension setup status in Forge.")
    return path.resolve()


def parse_preset(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_PRESET_BYTES:
        raise ValueError("Preset must be a JSON file no larger than 2 MB.")
    try:
        preset = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError("The preset is not valid JSON.") from exc
    if not isinstance(preset, dict) or preset.get("format") != PRESET_FORMAT or not isinstance(preset.get("settings"), dict):
        raise ValueError("Export a settings preset from Visual Enhancer and select its JSON file.")
    enabled = preset["settings"].get("image_enabled_stages")
    if not isinstance(enabled, list) or not enabled or not all(isinstance(x, str) for x in enabled):
        raise ValueError("The preset has no enabled image effects. Enable an effect before exporting it.")
    return preset


def with_standard_shaders(preset, shader_pack=None):
    """Add the standard pack as a search fallback without changing custom paths."""
    settings = preset.get("settings", {}) if isinstance(preset, dict) else {}
    if not isinstance(settings, dict) or not isinstance(settings.get("image_enabled_stages"), list) or "reshade" not in settings["image_enabled_stages"]:
        return preset
    pack = Path(shader_pack) if shader_pack is not None else bootstrap.SHADER_PACK
    if not bootstrap.shader_pack_ready(pack):
        return preset
    result = copy.deepcopy(preset)
    destination = result["settings"]
    for name, folder in (("reshade_image_shader_search_paths", "Shaders"),
                         ("reshade_image_texture_search_paths", "Textures")):
        current = destination.get(name, "")
        if current is None:
            current = ""
        if not isinstance(current, str):
            continue
        new_path = (pack / folder).resolve().as_posix()
        existing = [p.strip() for p in current.split(";") if p.strip()]
        if not any(os.path.normcase(p.replace("/", "\\")) == os.path.normcase(new_path.replace("/", "\\")) for p in existing):
            existing.append(new_path)
        destination[name] = ";".join(existing)
    return result


def quick_preset(neural, style, strength, passes, tone, structure, skin, mask,
                 dlss, dlss_mode, dlss_preset, ai_upscale, ai_factor,
                 sharpen, sharp_method, sharpness, grain, grain_amount, grain_size):
    enabled = [stage for flag, stage in ((neural, "neural_model"), (dlss, "dlss_super_resolution"),
               (ai_upscale, "visionnext"), (sharpen, "cas_sharpening"), (grain, "grain")) if flag]
    if not enabled:
        raise ValueError("Enable at least one image effect.")
    if style not in ("Style 0", "Style 1", "Style 2") or dlss_mode not in ("DLAA", "Quality", "Balanced", "Performance", "Ultra Performance"):
        raise ValueError("Invalid neural style or DLSS mode.")
    if dlss_preset not in ("Default", "J", "K", "L", "M") or ai_factor not in ("2x", "4x") or sharp_method not in ("AMD CAS", "NVIDIA NIS"):
        raise ValueError("Invalid upscaling or sharpening setting.")
    def number(value, low, high, name, integer=False):
        import math
        if isinstance(value, bool):
            raise ValueError("Invalid " + name)
        n = float(value)
        if not math.isfinite(n) or not low <= n <= high or (integer and n != int(n)):
            raise ValueError("Invalid " + name)
        return int(n) if integer else n
    settings = {
        "image_stage_order": STAGES, "image_enabled_stages": enabled,
        "nr_style": style, "nr_intensity": number(strength, 0, 2, "strength"),
        "nr_passes": number(passes, 1, 4, "passes", True),
        "local_tone_strength": number(tone, 0, 1, "tone"),
        "local_structure_strength": number(structure, 0, 1, "structure"),
        "skin_structure_strength": number(skin, 0, 1, "skin"), "automatic_mask": bool(mask),
        "upscale_image_dlss_mode": dlss_mode, "upscale_image_dlss_preset": dlss_preset,
        "upscale_image_model": "VisionNext", "upscale_image_visionnext_scale": int(ai_factor[0]),
        "upscale_image_visionnext_gpu": "auto", "upscale_image_visionnext_tile": 0,
        "upscale_ai_framework": "directml", "sharpening_method": sharp_method,
        "cas_sharpness": number(sharpness, 0, 100, "sharpness", True),
        "grain_amount": number(grain_amount, 0, 100, "grain", True),
        "grain_size": number(grain_size, 0.1, 10, "grain size"),
        "image_format": "PNG", "image_bit_depth": 8,
    }
    return {"format": PRESET_FORMAT, "schema_version": 43,
            "name": "Forge Visual Enhancer", "settings": settings}


@contextlib.contextmanager
def gpu_lock_if_needed(lock):
    # The user's patched Forge locks the complete generation, including this
    # callback. Reacquiring that non-reentrant lock would deadlock a batch.
    # Generic Forge owns its own generation lock around the callback.
    state = getattr(lock, "_thread_state", None)
    if state is None or getattr(state, "lock_fd", None) is not None:
        yield
    else:
        with lock:
            yield


def _stop_child(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15, check=False)
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=15)


def render(image, preset, executable=None, interrupted=lambda: False, timeout=600, dry_run=False):
    """Return a new PIL image on success; throw on errors so caller retains original."""
    exe = Path(executable) if executable else find_executable()
    with tempfile.TemporaryDirectory(prefix="forge_ve_") as work:
        folder = Path(work)
        source, target, spec = folder / "input.png", folder / "output.png", folder / "preset.json"
        image.save(source, format="PNG")
        spec.write_text(json.dumps(with_standard_shaders(preset), ensure_ascii=False), encoding="utf-8")
        args = [str(exe), "render", str(source), "--preset", str(spec), "-o", str(target),
                "--format", "png", "--json", "--quiet"]
        if dry_run:
            args.append("--dry-run")
        # Files, rather than pipes, keep verbose child output from filling a pipe.
        with (folder / "out.log").open("w+b") as out, (folder / "err.log").open("w+b") as err:
            proc = subprocess.Popen(args, cwd=str(exe.parent), stdout=out, stderr=err,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            started = time.monotonic()
            try:
                while proc.poll() is None:
                    if interrupted() or time.monotonic() - started > timeout:
                        raise TimeoutError("Enhancement was interrupted or exceeded the time limit.")
                    time.sleep(0.25)
            finally:
                if proc.poll() is None:
                    _stop_child(proc)
            out.seek(0)
            err.seek(0)
            stdout = out.read(1024 * 1024).decode("utf-8", "replace")
            stderr = err.read(4096).decode("utf-8", "replace").strip()
        try:
            result = json.loads(stdout)
        except ValueError as exc:
            raise RuntimeError("Visual Enhancer returned an unreadable result. " + stderr[-1000:]) from exc
        if proc.returncode != 0 or not result.get("ok") or (not dry_run and (result.get("completed") != 1 or result.get("failed") != 0)):
            raise RuntimeError("Visual Enhancer failed: " + (stderr[-1000:] or str(result.get("error") or result)))
        if dry_run:
            return result
        if not target.is_file():
            raise RuntimeError("Visual Enhancer did not produce the expected image.")
        with Image.open(target) as output:
            output.load()
            rendered = output.copy()
        rendered.info.update(image.info)
        return rendered
