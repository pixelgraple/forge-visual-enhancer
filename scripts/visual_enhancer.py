"""Visual Enhancer's still-image pipeline, available in txt2img and img2img."""
from pathlib import Path
import sys

import gradio as gr
from modules import scripts, shared

EXTENSION_DIR = str(Path(__file__).resolve().parent.parent)
if EXTENSION_DIR not in sys.path:
    sys.path.insert(0, EXTENSION_DIR)
from forge_visual_enhancer import bootstrap, engine


def _uploaded_preset(data):
    if data is None:
        return "", "Choose a preset exported by Visual Enhancer."
    try:
        if len(data) > engine.MAX_PRESET_BYTES:
            raise ValueError("Preset exceeds 2 MB.")
        raw = data.decode("utf-8-sig")
        preset = engine.parse_preset(raw)
        names = ", ".join(preset["settings"]["image_enabled_stages"])
        return raw, "Preset loaded. Image effects: " + names
    except (ValueError, UnicodeDecodeError) as exc:
        return "", "Could not load preset: " + str(exc)


def _mode_change(mode):
    return gr.update(visible=mode == "Quick settings"), gr.update(visible=mode == "Visual Enhancer preset")


class Script(scripts.Script):
    def title(self):
        return "Visual Enhancer (DLSS 5)"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion("Visual Enhancer (DLSS 5)", open=False):
            gr.Markdown("Small still-image enhancer · Runs after each finished image, before Forge saves it. "
                        "Needs an installed Visual Enhancer and a compatible GPU. Errors keep the original image.")
            setup_status = gr.Markdown(value=bootstrap.setup_message, every=3)
            retry_setup = gr.Button("Retry setup", size="sm", variant="secondary")
            retry_setup.click(bootstrap.start_setup, inputs=None, outputs=setup_status, show_progress="hidden")
            with gr.Accordion("Installed ReShade shader folders", open=False):
                gr.Markdown("Use these folders in the Visual Enhancer desktop app. In Forge, they are added to ReShade preset search paths automatically.")
                gr.Textbox(value=str(bootstrap.SHADER_PACK / "Shaders"), label="Shader folder", interactive=False, show_copy_button=True)
                gr.Textbox(value=str(bootstrap.SHADER_PACK / "Textures"), label="Texture folder", interactive=False, show_copy_button=True)
            enabled = gr.Checkbox(label="Enhance each image", value=False)
            mode = gr.Radio(["Quick settings", "Visual Enhancer preset"], value="Quick settings", label="Settings")
            with gr.Group(visible=True) as quick:
                neural = gr.Checkbox(label="Neural rendering", value=True, info="Apply the DLSS 5 neural image effect.")
                with gr.Row():
                    style = gr.Dropdown(["Style 0", "Style 1", "Style 2"], value="Style 1", label="Style")
                    strength = gr.Slider(0, 2, value=0.55, step=0.05, label="Strength")
                    passes = gr.Slider(1, 4, value=3, step=1, label="Passes")
                with gr.Accordion("Neural detail", open=False):
                    tone = gr.Slider(0, 1, value=0.7, step=0.05, label="Tone")
                    structure = gr.Slider(0, 1, value=0.7, step=0.05, label="Structure")
                    skin = gr.Slider(0, 1, value=0.7, step=0.05, label="Skin structure")
                    mask = gr.Checkbox(value=True, label="Automatic mask")
                with gr.Accordion("Upscaling and finishing", open=False):
                    dlss = gr.Checkbox(value=False, label="DLSS super resolution", info="May increase image dimensions.")
                    with gr.Row():
                        dlss_mode = gr.Dropdown(["DLAA", "Quality", "Balanced", "Performance", "Ultra Performance"], value="DLAA", label="DLSS mode")
                        dlss_preset = gr.Dropdown(["Default", "J", "K", "L", "M"], value="Default", label="DLSS preset")
                    ai_upscale = gr.Checkbox(value=False, label="VisionNext AI upscale")
                    ai_factor = gr.Radio(["2x", "4x"], value="2x", label="AI upscale factor")
                    sharpen = gr.Checkbox(value=True, label="Sharpen")
                    with gr.Row():
                        sharp_method = gr.Dropdown(["AMD CAS", "NVIDIA NIS"], value="AMD CAS", label="Sharpening method")
                        sharpness = gr.Slider(0, 100, value=50, step=1, label="Sharpness")
                    grain = gr.Checkbox(value=False, label="Film grain")
                    with gr.Row():
                        grain_amount = gr.Slider(0, 100, value=20, step=1, label="Grain amount")
                        grain_size = gr.Slider(0.1, 10, value=1, step=0.1, label="Grain size")
            with gr.Group(visible=False) as advanced:
                gr.Markdown("For the complete still-image pipeline and stage order, export a JSON settings preset "
                            "from Visual Enhancer and upload it here. Standard ReShade shaders are installed automatically "
                            "and added to the shader search path. Custom ReShade and LUT files referenced by the preset "
                            "must remain available on this computer. Video-only effects are not used for Forge images.")
                preset_file = gr.File(label="Visual Enhancer settings preset (.json)", file_types=[".json"], type="binary")
                preset_status = gr.Markdown("No preset loaded.")
                preset_json = gr.Textbox(label="Preset JSON", lines=3, info="Loaded from your file; you can also paste a preset.")
                preset_file.change(_uploaded_preset, inputs=preset_file, outputs=[preset_json, preset_status], show_progress="hidden")
            mode.change(_mode_change, inputs=mode, outputs=[quick, advanced], show_progress="hidden")
            gr.Markdown("The current generation keeps the shared GPU queue until enhancement finishes. "
                        "Leave this off to generate normally.")
        return [enabled, mode, preset_json, neural, style, strength, passes, tone, structure, skin, mask,
                dlss, dlss_mode, dlss_preset, ai_upscale, ai_factor, sharpen, sharp_method,
                sharpness, grain, grain_amount, grain_size]

    def postprocess_image_after_composite(self, p, pp, enabled, mode, preset_json, *quick_values):
        if not enabled:
            return
        # WAN's multi-frame video path uses this image hook for every frame.
        if getattr(getattr(shared, "sd_model", None), "is_wan", False) and getattr(p, "batch_size", 1) > 1:
            p.comments["Visual Enhancer skipped: video frames are not supported by this still-image extension."] = 1
            return
        p.extra_generation_params.pop("Visual Enhancer", None)
        try:
            if mode == "Quick settings":
                preset = engine.quick_preset(*quick_values)
            elif mode == "Visual Enhancer preset":
                preset = engine.parse_preset(preset_json)
            else:
                raise ValueError("Choose a valid Visual Enhancer settings mode.")
            from modules.call_queue import queue_lock
            with engine.gpu_lock_if_needed(queue_lock):
                enhanced = engine.render(pp.image, preset,
                    interrupted=lambda: bool(getattr(shared.state, "interrupted", False)))
            pp.image = enhanced
            p.extra_generation_params["Visual Enhancer"] = "Applied (" + mode + ")"
        except Exception as exc:
            message = "Visual Enhancer could not process an image; original kept: " + str(exc)
            print("[Forge Visual Enhancer] " + message, flush=True)
            p.comments[message] = 1
