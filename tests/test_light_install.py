"""Regression checks for the light installation and optional photo preparation."""
import subprocess
import sys
import unittest

from helpers import ROOT


class LightInstall(unittest.TestCase):
    def test_light_requirements_exclude_photo_packages(self):
        names = {line.split("==")[0] for line in (ROOT / "requirements.txt").read_text().splitlines()
                 if line and not line.startswith("#")}
        self.assertEqual(names, {"numpy", "pillow", "pyyaml"})

    def test_text_checks_never_import_photo_packages(self):
        # Run the real CLI in a fresh process: an attempted import fails even on
        # a developer machine that already has the optional packages installed.
        program = '''
import importlib.abc
import sys

class NoPhotoImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "torchvision", "transformers", "huggingface_hub", "cv2"}:
            raise AssertionError("light check imported " + fullname)

sys.meta_path.insert(0, NoPhotoImports())
import cinetty
from cinetty.cli import main
for template in ("loop-landscape", "loop-portrait", "pipeline", "screen-flow", "circuit-flow"):
    assert main(["check", template, "--format", "json"]) == 0, template
assert not any(name.split(".")[0] == "torch" for name in sys.modules)
'''
        r = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_uncached_photo_preparation_names_the_install_command(self):
        # Hide only the optional packages, leaving the actual sample files and
        # preparation entry points intact. No model inference or API is used.
        program = '''
from unittest.mock import patch
from cinetty import photos
for prepare, project in (
    (photos.prepare, "examples/harness-photo/project.en.yaml"),
):
    with patch("importlib.util.find_spec", return_value=None):
        try:
            if prepare is photos.prepare:
                prepare(project, force=True)
            else:
                prepare(project)
        except SystemExit as e:
            assert "make setup-photo" in str(e), str(e)
        else:
            raise AssertionError("photo preparation should require make setup-photo")
'''
        r = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
