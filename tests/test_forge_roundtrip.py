"""Exercise the installed Forge serializers without starting Forge or a GPU job.

Set FORGE_TEST_ROOT to a Forge checkout to run these checks.
"""
import ast
import base64
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import piexif
import piexif.helper
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge_visual_enhancer import attribution


def function_from_source(path, name, namespace):
    source = ast.parse(path.read_text(encoding="utf-8"))
    definition = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[definition], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


@unittest.skipUnless(os.environ.get("FORGE_TEST_ROOT"), "Set FORGE_TEST_ROOT to test the installed Forge serializers")
class ForgeMetadataRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        forge = Path(os.environ["FORGE_TEST_ROOT"])
        cls.opts = types.SimpleNamespace(enable_pnginfo=True, samples_format="png", jpeg_quality=95, webp_lossless=True,
                                         CLIP_stop_at_last_layers=1, eta_noise_seed_delta=0, scaling_factor=1,
                                         add_model_hash_to_info=False, add_model_name_to_info=False,
                                         inpainting_mask_weight=1, add_version_to_infotext=False,
                                         add_user_name_to_info=False, forge_unet_storage_dtype="Automatic",
                                         forge_additional_modules=[], save_init_img=False, randn_source="GPU", tiling=False)
        namespace = {"os": os, "Image": Image, "PngImagePlugin": PngImagePlugin,
                     "piexif": piexif, "opts": cls.opts}
        cls.save = staticmethod(function_from_source(forge / "modules" / "images.py", "save_image_with_geninfo", namespace))
        namespace = {"io": io, "base64": base64, "Image": Image, "PngImagePlugin": PngImagePlugin,
                     "piexif": piexif, "opts": cls.opts}
        cls.encode = staticmethod(function_from_source(forge / "modules" / "api" / "api.py", "encode_pil_to_base64", namespace))
        namespace = {"os": os, "opts": cls.opts, "shared": types.SimpleNamespace(opts=cls.opts),
                     "_overridden_modules": None,
                     "get_noise_source_type": lambda: "GPU",
                     "infotext_utils": types.SimpleNamespace(quote=str),
                     "errors": types.SimpleNamespace(report=lambda *args, **kwargs: None)}
        cls.infotext = staticmethod(function_from_source(forge / "modules" / "processing.py", "create_infotext", namespace))

    def test_real_infotext_attributes_each_success_and_partial_grid(self):
        model = types.SimpleNamespace(use_distilled_cfg_scale=False, use_shift=False, is_sd1=False)
        p = types.SimpleNamespace(extra_generation_params={}, iteration=0, batch_size=2,
                                  main_prompt="A test prompt", main_negative_prompt="",
                                  all_negative_prompts=["", ""], all_seeds=[11, 12],
                                  all_subseeds=[0, 0], sd_model=model, steps=12,
                                  sampler_name="test", scheduler="test", cfg_scale=7,
                                  restore_faces=False, is_using_inpainting_conditioning=False,
                                  width=16, height=16, subseed_strength=0,
                                  seed_resize_from_w=0, seed_resize_from_h=0, tiling=False,
                                  get_token_merging_ratio=lambda **kwargs: 0)
        image = Image.new("RGB", (16, 16), "blue")
        attribution.mark_processed(p, image, 0, "Quick settings")
        args = (p, ["A test prompt", "Second prompt"], [11, 12], [0, 0])
        first = self.infotext(*args, index=0)
        second = self.infotext(*args, index=1)
        grid = self.infotext(*args, use_main_prompt=True)
        self.assertIn(attribution.CREDIT, first)
        self.assertIn(attribution.LICENSE_KEY, first)
        self.assertNotIn(attribution.CREDIT, second)
        self.assertNotIn(attribution.LICENSE_KEY, second)
        self.assertIn(attribution.CREDIT, grid)
        self.assertIn(attribution.LICENSE_KEY, grid)

    def test_actual_forge_queue_stays_owned_while_other_thread_enhances(self):
        from test_extension import ARGS, load_script
        from forge_visual_enhancer import engine

        forge = Path(os.environ["FORGE_TEST_ROOT"])
        queue_spec = importlib.util.spec_from_file_location("ve_test_shared_queue", forge / "modules" / "shared_generation_queue.py")
        queue_module = importlib.util.module_from_spec(queue_spec)
        queue_spec.loader.exec_module(queue_module)
        fifo_spec = importlib.util.spec_from_file_location("ve_test_fifo", forge / "modules" / "fifo_lock.py")
        fifo_module = importlib.util.module_from_spec(fifo_spec)
        fifo_spec.loader.exec_module(fifo_module)
        script_module, fake = load_script()
        render_started, release_render, render_finished = threading.Event(), threading.Event(), threading.Event()
        contender_acquired = threading.Event()
        failures = []

        def finish_image():
            try:
                script_module.Script().postprocess_image_after_composite(
                    p, pp, True, "Quick settings", "", *ARGS)
            except BaseException as exc:
                failures.append(exc)
            finally:
                render_finished.set()

        def simulated_render(*args, **kwargs):
            render_started.set()
            if not release_render.wait(5):
                raise TimeoutError("Test render was not released")
            return Image.new("RGB", (16, 16), "red")

        with tempfile.TemporaryDirectory(prefix="ve-queue-regression-") as folder, \
             patch.dict(os.environ, {"SD_SHARED_QUEUE_DIR": folder}):
            owner = queue_module.SharedGenerationLock(fifo_module.FIFOLock(), instance_name="test-owner")
            contender = queue_module.SharedGenerationLock(fifo_module.FIFOLock(), instance_name="test-contender")
            fake["modules.call_queue"].queue_lock = owner
            p = types.SimpleNamespace(comments={}, extra_generation_params={}, batch_size=1, iteration=0)
            pp = types.SimpleNamespace(image=Image.new("RGB", (16, 16), "blue"), index=0)

            def compete():
                with contender:
                    contender_acquired.set()

            worker = threading.Thread(target=finish_image, daemon=True)
            other = threading.Thread(target=compete, daemon=True)
            with patch.dict(sys.modules, fake), patch.object(engine, "render", side_effect=simulated_render):
                try:
                    with owner:
                        worker.start()
                        self.assertTrue(render_started.wait(3), "Enhancement blocked on the caller's queue")
                        other.start()
                        self.assertFalse(contender_acquired.wait(.4), "A second operation entered the GPU queue")
                        release_render.set()
                        self.assertTrue(render_finished.wait(3))
                        self.assertFalse(contender_acquired.is_set())
                    self.assertTrue(contender_acquired.wait(3))
                finally:
                    release_render.set()
                    worker.join(timeout=4)
                    if other.ident is not None:
                        other.join(timeout=4)
            self.assertFalse(failures)
            self.assertFalse(worker.is_alive())
            self.assertFalse(other.is_alive())
            self.assertEqual(pp.image.getpixel((0, 0)), (255, 0, 0))

    def test_saved_files_and_api_images_retain_credit_and_prompt(self):
        prompt = "A test prompt\nSteps: 12, Visual Enhancer: " + attribution.STAMP
        for extension, mode in (("png", "RGB"), ("png", "RGBA"), ("jpg", "RGB"),
                                ("jpg", "RGBA"), ("webp", "RGB"), ("webp", "RGBA")):
            with self.subTest(extension=extension, mode=mode), tempfile.TemporaryDirectory() as folder:
                self.opts.samples_format = extension
                image = Image.new(mode, (16, 16), "#72a9ba")
                image.info["parameters"] = prompt
                image.info[attribution.FIELD] = attribution.CREDIT
                image.info[attribution.LICENSE_FIELD] = attribution.LICENSE_KEY
                path = Path(folder) / ("image." + extension)
                self.save(image, prompt, str(path), "." + extension,
                          existing_pnginfo={attribution.FIELD: attribution.CREDIT,
                                            attribution.LICENSE_FIELD: attribution.LICENSE_KEY})
                with Image.open(path) as saved:
                    self.assertIn(attribution.CREDIT, read_prompt(saved, extension))
                    self.assertIn(attribution.LICENSE_KEY, read_prompt(saved, extension))
                    self.assertIn("A test prompt", read_prompt(saved, extension))
                    if extension == "png":
                        self.assertEqual(saved.info[attribution.FIELD], attribution.CREDIT)
                        self.assertEqual(saved.info[attribution.LICENSE_FIELD], attribution.LICENSE_KEY)

                encoded = self.encode(image)
                with Image.open(io.BytesIO(base64.b64decode(encoded))) as returned:
                    self.assertIn(attribution.CREDIT, read_prompt(returned, extension))
                    self.assertIn(attribution.LICENSE_KEY, read_prompt(returned, extension))
                    self.assertIn("A test prompt", read_prompt(returned, extension))


def read_prompt(image, extension):
    if extension == "png":
        return image.info.get("parameters", "")
    exif = piexif.load(image.info["exif"])
    return piexif.helper.UserComment.load(exif["Exif"][piexif.ExifIFD.UserComment])


if __name__ == "__main__":
    unittest.main(verbosity=2)
