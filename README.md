# Visual Enhancer for Forge Neo

This extension adds an optional **Visual Enhancer (DLSS 5)** panel to Forge
Neo's txt2img and img2img screens. Each enabled still image is processed after
compositing, before Forge saves and returns it. The original is retained if
enhancement fails. The extension is disabled by default.

## Installation through Forge

In Forge, open **Extensions → Install from URL**, enter the repository address,
and choose **Install**. Apply and restart the Forge UI when prompted. Existing
generation work should be allowed to finish before restarting.

Forge executes this repository's `install.py` after cloning it. Setup reuses a
complete existing Visual Enhancer installation when one is configured or found
in a common location. Otherwise, it downloads the original official v20.0
Windows archive directly from its author, verifies SHA-256, and installs it
inside this extension. The download is approximately 904 MB and the extracted
application needs additional disk space. The download and extraction run in
the background; the extension panel reports progress and can retry failures.
No packaged Visual Enhancer binaries or model files are present in this repo.

## Credits and attribution

**Visual Enhancer is created by Merserk.** This extension runs the original
Visual Enhancer application and does not claim ownership of it. The tested
v20.0 archive is downloaded directly from Merserk's official release:

- [Official v20.0 release page](https://github.com/Merserk/dlss5-visual-enhancer/releases/tag/v20.0)
- [Exact application archive used by the installer](https://github.com/Merserk/dlss5-visual-enhancer/releases/download/v20.0/Visual.Enhancer.v20.0.7Zip-Ultra.zip)

Merserk's Visual Enhancer and its third-party components retain their own
copyright and license terms. This repository contains the Forge integration;
it does not relicense Visual Enhancer or its dependencies. The application is
an independent project and is not affiliated with or endorsed by NVIDIA.

Each image successfully processed by this extension receives the Visual
Enhancer and Merserk credit and the distribution license key in its generation
metadata. The key is included with this public extension and is readable from
processed images. To avoid producing enhanced images without that metadata,
Forge's **Write infotext to metadata of generated images** setting must be
enabled and image format must be PNG, JPEG, or WebP. If saved grids are enabled,
their format must also be PNG, JPEG, or WebP. If these settings cannot preserve
the required metadata, the extension keeps the original image and reports the
reason.

Setup also downloads the pinned standard ReShade shader collection from its
official upstream repository, verifies its SHA-256, and keeps its original
files and notices under `runtime/reshade-standard`. Existing shader folders are
never overwritten. Both `Shaders` and `Textures` are added as fallback search
paths for enabled ReShade image presets, while custom search paths are retained.
The standard collection supplies five effects and associated include files; it
does not automatically enable any effect. Different shader packs may have
different licenses and compatibility requirements.

Windows and a compatible NVIDIA GPU are required for the GPU effects. The
application's own license and requirements apply. To select a portable copy
outside the common locations, set the environment variable
`VISUAL_ENHANCER_EXE` to the full path of its `VE_CLI.exe` before starting
Forge, or configure that path in the local, untracked `config.json`. The GUI
executable must be beside it. Version 20.0 is the tested target.

## Using the panel

Enable **Enhance each image** and choose the effects in **Quick settings**.
For the complete still-image pipeline, including custom stage order, ReShade,
LUTs, and advanced options, export a JSON settings preset from the Visual
Enhancer desktop program and upload it under **Visual Enhancer preset**.
Referenced shaders, LUTs and other external resources must remain available at
their saved paths. Video-only effects and frame generation are not applied to
Forge's still-image output.

On installations with the shared Forge GPU queue, enhancement stays within
the existing generation lock; it does not re-enter the lock or restart another
Forge process. Enhancement can take additional time and VRAM.
