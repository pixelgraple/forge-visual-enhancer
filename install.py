"""Forge calls this after Git clone and during normal extension startup."""
import sys
from forge_visual_enhancer import bootstrap

if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        bootstrap._worker()
    else:
        print("[Forge Visual Enhancer] " + bootstrap.start_setup(), flush=True)
