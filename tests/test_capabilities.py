"""Prerequisite discovery must not execute optional inference code."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from spatialmind.capabilities import collect_capabilities

ROOT = Path(__file__).resolve().parents[1]


class CapabilityTests(unittest.TestCase):
    def test_discovery_does_not_promote_found_packages_to_readiness(self):
        with patch("spatialmind.capabilities.importlib.util.find_spec", return_value=object()) as find:
            with patch("spatialmind.capabilities.shutil.which", return_value="/private/tool"):
                result = collect_capabilities()
        self.assertEqual([call.args for call in find.call_args_list], [("torch",), ("cv2",)])
        self.assertEqual(result["module_discovery"], {"torch": "found", "cv2": "found"})
        self.assertTrue(result["nvidia_smi_on_path"])
        self.assertEqual(result["inference_readiness"], "unverified")
        self.assertEqual(result["checkpoint_authorization"], "unverified")
        for key in ("model_revision", "input_resolution", "throughput_fps"):
            self.assertIsNone(result[key])
        self.assertNotIn("/private/tool", json.dumps(result))

    def test_failed_discovery_is_distinct_from_missing(self):
        with patch("spatialmind.capabilities.importlib.util.find_spec",
                   side_effect=[ValueError("private module location"), None]):
            with patch("spatialmind.capabilities.shutil.which", return_value=None):
                with patch("spatialmind.capabilities.os.cpu_count", return_value=None):
                    result = collect_capabilities()
        self.assertEqual(result["module_discovery"], {"torch": "unknown", "cv2": "missing"})
        self.assertIsNone(result["logical_cpu_count"])
        self.assertFalse(result["nvidia_smi_on_path"])
        self.assertNotIn("private module location", json.dumps(result))

    def test_ram_probe_is_optional_and_not_available_memory(self):
        from spatialmind.capabilities import _total_ram_bytes
        with patch("spatialmind.capabilities.os.sysconf", side_effect=[100, 4096], create=True):
            self.assertEqual(_total_ram_bytes(), 409600)
        with patch("spatialmind.capabilities.os.sysconf", side_effect=ValueError, create=True):
            self.assertIsNone(_total_ram_bytes())

    def test_cli_works_without_site_packages_and_optional_imports(self):
        script = """
import importlib.abc
import runpy
import sys
class DenyOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ("torch", "cv2"):
            raise ImportError("blocked for offline test")
sys.meta_path.insert(0, DenyOptional())
sys.argv = ["spatialmind.capabilities", "--json"]
runpy.run_module("spatialmind.capabilities", run_name="__main__")
"""
        run = subprocess.run([sys.executable, "-S", "-c", script], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["module_discovery"], {"torch": "unknown", "cv2": "unknown"})
        self.assertEqual(result["scope"], "current_execution_runtime")
        self.assertEqual(result["inference_readiness"], "unverified")

    def test_discoverable_package_code_is_not_executed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("torch", "cv2"):
                Path(tmp, name + ".py").write_text("raise RuntimeError('must not execute')\n")
            script = """
import sys
sys.path.insert(0, sys.argv[1])
from spatialmind.capabilities import main
main(["--json"])
assert "torch" not in sys.modules and "cv2" not in sys.modules
"""
            run = subprocess.run([sys.executable, "-S", "-c", script, tmp], cwd=ROOT,
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["module_discovery"],
                         {"torch": "found", "cv2": "found"})


if __name__ == "__main__":
    unittest.main()
