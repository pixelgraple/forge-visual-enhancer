# Visual Enhancer for Forge Neo

This extension adds an optional **Visual Enhancer (DLSS 5)** panel to Forge
Neo's txt2img and img2img screens. Each enabled still image is processed after
compositing, before Forge saves and returns it. The original is retained if
enhancement fails. The extension is disabled by default.

## Quick install: paste the URL and click Install

**Windows · Forge Neo / Forge Classic · compatible NVIDIA GPU · internet required**

Paste this address into Forge's **Extensions → Install from URL**:

```text
https://github.com/pixelgraple/forge-visual-enhancer.git
```

1. Click **Install** once. Leave the optional directory and branch fields blank.
   Visual Enhancer and the standard ReShade shaders are prepared automatically.
2. When all generation jobs have finished, fully stop and relaunch Forge using
   your usual launcher. This is Forge's normal extension-loading step; simply
   refreshing the browser is not enough.
3. Open **Visual Enhancer (DLSS 5)** under **txt2img** or **img2img**. Wait until
   **Setup** says Visual Enhancer and the standard ReShade shaders are **ready**.
4. Check **Enhance each image**, choose your settings, and generate as usual.

There is no separate app installer, pip command, shader download, file copying,
executable-path setup, or license-key entry on the normal installation path.
The extension starts disabled so you choose when to add enhancement to a job.

The first setup downloads approximately **904 MB**, plus a small shader pack,
and needs additional space for the extracted application. Allow the download
to finish; its time depends on your connection. Installing the GitHub extension
finishes before this background download does.

Forge executes this repository's `install.py` after cloning it. Setup reuses a
complete existing Visual Enhancer installation when one is configured or found
in a common location. Otherwise, it downloads the original official v20.0
Windows archive directly from its author, verifies SHA-256, and installs it
inside this extension. The download is approximately 904 MB and the extracted
application needs additional disk space. The download and extraction run in
the background; the extension panel reports progress. Status polling stops when
setup is ready. **Retry setup** appears only when setup needs attention.
No packaged Visual Enhancer binaries or model files are present in this repo.

## Updating an existing installation

Open **Extensions → Installed**, click **Check for updates**, and apply the
update for **forge-visual-enhancer** using Forge's update controls. Wait for
all generation work to finish before applying an update that restarts Forge.
Then make sure the **Forge Python process has fully restarted**, using your
usual launcher if needed. A browser refresh or a UI-only reload can retain
the old Python code. Refresh the browser after Forge is back.

Updates preserve the local runtime, shader pack, and `config.json`; a complete
existing installation does not download the application again. If you run
multiple Forge instances, update each extension copy and restart each instance
when its queue is idle.

The current update fixes the shared-queue lockup after generation and removes
the repeated setup polling and unnecessary Retry button. See
[the change notes](CHANGELOG.md).

## If setup needs attention

- **Downloading / preparing:** let setup finish. Keep Forge open and connected
  to the internet. You do not need to keep clicking Install.
- **Ready:** setup is complete. No Retry button is expected.
- **Download failed:** check your connection to GitHub, then click **Retry setup**.
  Setup checks the official download's SHA-256 before installing it.
- **An existing configuration or folder is incomplete:** the status explains
  what needs attention. Existing user files are preserved; retrying will not
  overwrite them. Repair the named installation/path first.
- **The old panel is still showing:** finish active jobs, fully restart Forge,
  and refresh its browser tab.

Setup status and errors are recorded in
`extensions/forge-visual-enhancer/.setup/status.json`. Worker details are in
`.setup/install.log`; errors before the worker starts can also appear in
Forge's console.

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

**Standard ReShade shaders by crosire and contributors:**
[upstream source and notices](https://github.com/crosire/reshade-shaders/tree/fd0022170615ce0d8162d219bff07232fa6dd84f).

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

## Installation verification for developers

Run `python tests/smoke_fresh_install.py` with Forge's Python interpreter on
Windows to test a clean installation in a temporary folder. This downloads the
full official application and shaders, verifies readiness and CLI startup, and
checks that a second install call reuses the completed setup. It does not run
an image generation or modify a live Forge installation.
