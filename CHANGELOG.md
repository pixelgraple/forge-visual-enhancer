# Change notes

## 2026-11-13

- Fixed a cross-thread deadlock that could leave an image waiting after sampling.
  Enhancement uses the GPU queue lock already held by Forge for that generation.
- Stop setup status polling when the application and shaders are ready; only show
  Retry setup when setup needs attention.
- Clarified URL installation, automatic dependencies, readiness, and the full
  Forge process restart required to load updated Python modules.
- Added a fresh-install check that downloads the official application and shaders
  into a temporary copy, checks CLI startup, and verifies repeat setup reuses them.

Existing automatic installation, per-image Merserk credit and distribution-key
metadata, supported presets, and original-image fallback remain available.
