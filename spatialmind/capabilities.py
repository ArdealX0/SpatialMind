"""Discover optional local prerequisites without loading inference libraries."""
import argparse
import importlib.util
import json
import os
import platform
import shutil


def _module_status(name):
    try:
        return "found" if importlib.util.find_spec(name) is not None else "missing"
    except (ImportError, ValueError, AttributeError):
        return "unknown"


def _total_ram_bytes():
    """OS-reported physical RAM, not process/container-available memory."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return pages * size if pages > 0 and size > 0 else None
    except (AttributeError, OSError, ValueError):
        return None


def collect_capabilities():
    """Describe this execution runtime; discovery never verifies inference."""
    return {
        "scope": "current_execution_runtime",
        "python_version": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "total_ram_bytes": _total_ram_bytes(),
        "module_discovery": {name: _module_status(name) for name in ("torch", "cv2")},
        "nvidia_smi_on_path": shutil.which("nvidia-smi") is not None,
        "inference_readiness": "unverified",
        "checkpoint_authorization": "unverified",
        "model_revision": None,
        "input_resolution": None,
        "throughput_fps": None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON (the default output format)")
    parser.parse_args(argv)
    print(json.dumps(collect_capabilities(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
