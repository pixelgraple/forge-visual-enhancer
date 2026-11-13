"""Record the Visual Enhancer credit on each successfully processed image."""

from . import bootstrap


FIELD = "Visual Enhancer Attribution"
LICENSE_FIELD = "Visual Enhancer License Key"
LICENSE_KEY = "758-cc-n4Ha"
CREDIT = "Visual Enhancer by Merserk; official download: " + bootstrap.RELEASE_URL
STAMP = CREDIT + "; License key: " + LICENSE_KEY
SUPPORTED_FORMATS = frozenset(("png", "jpg", "jpeg", "webp"))


def require_writable_metadata(options):
    """Do not produce an enhanced image when Forge would omit its credit."""
    if not getattr(options, "enable_pnginfo", False):
        raise ValueError("Enable 'Write infotext to metadata of generated images' in Forge settings.")
    sample_format = str(getattr(options, "samples_format", "")).lower().lstrip(".")
    if sample_format not in SUPPORTED_FORMATS:
        raise ValueError("Select PNG, JPEG, or WebP as Forge's image format so attribution can be saved.")
    if getattr(options, "grid_save", False):
        grid_format = str(getattr(options, "grid_format", "")).lower().lstrip(".")
        if grid_format not in SUPPORTED_FORMATS:
            raise ValueError("Select PNG, JPEG, or WebP as Forge's saved grid format so attribution can be saved.")


class _PerImageCredit(str):
    """Forge evaluates callable infotext values per image and for the grid.

    Subclassing str keeps Processed.js() serializable after the batch completes.
    """

    def __new__(cls, processed):
        result = super().__new__(cls, STAMP)
        result.processed = processed
        return result

    def __call__(self, p=None, index=0, use_main_prompt=False, **_):
        if use_main_prompt:
            return "Contains images enhanced with " + STAMP if self.processed else None
        image_index = int(getattr(p, "iteration", 0)) * int(getattr(p, "batch_size", 1)) + int(index or 0)
        mode = self.processed.get(image_index)
        return "Applied (" + mode + "); " + STAMP if mode is not None else None


def mark_processed(p, image, index, mode):
    """Mark only a successfully enhanced image, retaining its original info."""
    processed = getattr(p, "_visual_enhancer_processed", None)
    if processed is None:
        processed = {}
        p._visual_enhancer_processed = processed
    processed[int(index)] = str(mode)
    p.extra_generation_params["Visual Enhancer"] = _PerImageCredit(processed)
    image.info[FIELD] = CREDIT
    image.info[LICENSE_FIELD] = LICENSE_KEY


def before_image_saved(params):
    """Keep a separate PNG text field as well as Forge's credited infotext."""
    if params.image.info.get(FIELD) == CREDIT and params.image.info.get(LICENSE_FIELD) == LICENSE_KEY:
        params.pnginfo[FIELD] = CREDIT
        params.pnginfo[LICENSE_FIELD] = LICENSE_KEY
