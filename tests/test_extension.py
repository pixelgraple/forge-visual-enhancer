import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import gradio as gr
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forge_visual_enhancer import engine

ARGS = (True, "Style 1", .55, 3, .7, .7, .7, True, False, "DLAA", "Default",
        False, "2x", True, "AMD CAS", 50, False, 20, 1.)


def load_script():
    modules = types.ModuleType("modules")
    scripts = types.ModuleType("modules.scripts")
    scripts.Script = type("Script", (), {})
    scripts.AlwaysVisible = object()
    shared = types.ModuleType("modules.shared")
    shared.state = types.SimpleNamespace(interrupted=False)
    shared.sd_model = types.SimpleNamespace(is_wan=False)
    modules.scripts, modules.shared = scripts, shared
    call_queue = types.ModuleType("modules.call_queue")
    call_queue.queue_lock = types.SimpleNamespace()
    fake = {"modules": modules, "modules.scripts": scripts,
            "modules.shared": shared, "modules.call_queue": call_queue}
    spec = importlib.util.spec_from_file_location("test_forge_ve_script", ROOT / "scripts" / "visual_enhancer.py")
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake):
        spec.loader.exec_module(mod)
    return mod, fake


class EngineTests(unittest.TestCase):
    def test_quick_stage_values_and_validation(self):
        preset = engine.quick_preset(*ARGS)
        self.assertEqual(preset["settings"]["image_enabled_stages"], ["neural_model", "cas_sharpening"])
        bad = list(ARGS); bad[2] = float("nan")
        with self.assertRaises(ValueError): engine.quick_preset(*bad)
        bad = list(ARGS); bad[0] = bad[14] = False
        with self.assertRaises(ValueError): engine.quick_preset(*bad)

    def test_native_preset_is_preserved_and_requires_image_effect(self):
        preset = engine.quick_preset(*ARGS)
        preset["settings"].update({"image_stage_order": ["reshade", "neural_model"],
                                   "image_enabled_stages": ["reshade", "neural_model"],
                                   "reshade_image_preset_path": "C:/a/preset.ini", "unknown_future_field": {"x": [1, 2]}})
        self.assertEqual(engine.parse_preset(json.dumps(preset)), preset)
        preset["settings"]["image_enabled_stages"] = []
        with self.assertRaises(ValueError): engine.parse_preset(json.dumps(preset))

    def test_shared_lock_is_not_reacquired_when_current_thread_owns_it(self):
        class Lock:
            def __init__(self, held): self._thread_state = types.SimpleNamespace(lock_fd=1 if held else None); self.calls = []
            def __enter__(self): self.calls.append("acquire")
            def __exit__(self, *args): self.calls.append("release")
        held, free = Lock(True), Lock(False)
        with engine.gpu_lock_if_needed(held): pass
        with engine.gpu_lock_if_needed(free): pass
        self.assertEqual(held.calls, [])
        self.assertEqual(free.calls, ["acquire", "release"])

    def test_real_cli_dry_run(self):
        path = Path(os.environ.get("VISUAL_ENHANCER_TEST_EXE", ""))
        if not path.is_file(): self.skipTest("Optional local v20 installation not present")
        out = engine.render(Image.new("RGB", (64, 64), "blue"), engine.quick_preset(*ARGS), path, dry_run=True)
        self.assertEqual(out["items"][0]["stages"], ["neural_model", "cas_sharpening", "export"])


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.mod, self.fake = load_script()
        self.script = self.mod.Script()
        self.image = Image.new("RGB", (64, 64), "blue")
        self.p = types.SimpleNamespace(comments={}, extra_generation_params={}, batch_size=1)
        self.pp = types.SimpleNamespace(image=self.image)

    def test_gradio_panel_builds_in_both_tabs(self):
        for tab in (False, True):
            with gr.Blocks() as demo:
                components = self.script.ui(tab)
            self.assertEqual(len(components), 22)
            self.assertGreater(len(demo.config["dependencies"]), 0)

    def test_disabled_does_nothing_and_success_replaces_each_image(self):
        with patch.dict(sys.modules, self.fake), patch.object(engine, "render", return_value=Image.new("RGB", (64, 64), "red")) as render:
            self.script.postprocess_image_after_composite(self.p, self.pp, False, "Quick settings", "", *ARGS)
            self.assertEqual(render.call_count, 0)
            self.script.postprocess_image_after_composite(self.p, self.pp, True, "Quick settings", "", *ARGS)
            self.assertEqual(self.pp.image.getpixel((0, 0)), (255, 0, 0))
            self.assertIn("Visual Enhancer", self.p.extra_generation_params)
            self.script.postprocess_image_after_composite(self.p, self.pp, True, "Quick settings", "", *ARGS)
            self.assertEqual(render.call_count, 2)

    def test_failure_retains_original_and_reports_it(self):
        with patch.dict(sys.modules, self.fake), patch.object(engine, "render", side_effect=RuntimeError("test failure")):
            self.script.postprocess_image_after_composite(self.p, self.pp, True, "Quick settings", "", *ARGS)
        self.assertIs(self.pp.image, self.image)
        self.assertTrue(any("test failure" in x for x in self.p.comments))
        self.assertNotIn("Visual Enhancer", self.p.extra_generation_params)

    def test_video_frames_are_not_processed(self):
        self.fake["modules.shared"].sd_model.is_wan = True
        self.p.batch_size = 5
        with patch.dict(sys.modules, self.fake), patch.object(engine, "render") as render:
            self.script.postprocess_image_after_composite(self.p, self.pp, True, "Quick settings", "", *ARGS)
        render.assert_not_called()
        self.assertTrue(self.p.comments)

    def test_upload_loads_full_preset(self):
        preset = engine.quick_preset(*ARGS)
        raw, status = self.mod._uploaded_preset(json.dumps(preset).encode())
        self.assertEqual(json.loads(raw), preset)
        self.assertIn("neural_model", status)
        raw, status = self.mod._uploaded_preset(b"nope")
        self.assertFalse(raw)
        self.assertIn("Could not load", status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
