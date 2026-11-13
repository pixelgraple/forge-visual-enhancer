# Visual Enhancer for Forge Neo

This is a private development repository. Do not publish it or redistribute
Visual Enhancer unless its author has granted the required permission.

This extension adds an optional **Visual Enhancer (DLSS 5)** panel to Forge
Neo's txt2img and img2img screens. Each enabled still image is processed after
compositing, before Forge saves and returns it. The original is retained if
enhancement fails. The extension is disabled by default.

## Installation through Forge

In Forge, open **Extensions → Install from URL**, enter the repository address,
and choose **Install**. Private repositories require an authorized GitHub
account configured for Git on the installing computer. Apply and restart the
Forge UI when prompted. Existing generation work should be allowed to finish
before restarting.

Forge executes this repository's `install.py` after cloning it. Setup reuses a
complete existing Visual Enhancer installation when one is configured or found
in a common location. Otherwise, it downloads the original official v20.0
Windows archive directly from its author, verifies SHA-256, and installs it
inside this extension. The download is approximately 904 MB and the extracted
application needs additional disk space. The download and extraction run in
the background; the extension panel reports progress and can retry failures.
No packaged Visual Enhancer binaries or model files are present in this repo.

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
