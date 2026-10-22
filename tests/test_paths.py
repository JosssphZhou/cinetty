"""Exercise the real Make entry points with spaces and CJK in project paths."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class ProjectPaths(unittest.TestCase):
    def test_check_and_once_accept_spaces_and_chinese(self):
        with tempfile.TemporaryDirectory(prefix="path-check-", dir=ROOT) as directory:
            for relative in ("my service.yaml", "测试 目录/架构图.yaml"):
                project = Path(directory) / relative
                project.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / "examples/circuit-flow/project.en.yaml", project)
                for target in ("check", "once"):
                    with self.subTest(path=relative, target=target):
                        result = subprocess.run(
                            ["make", "--no-print-directory", "-s", target,
                             f"PY={sys.executable}", f"INPUT={project.relative_to(ROOT)}",
                             "FORMAT=json", "AT=12"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60,
                        )
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        if target == "check":
                            self.assertTrue(json.loads(result.stdout)["ok"])
                        else:
                            self.assertIn("made with cinetty", result.stdout)


if __name__ == "__main__":
    unittest.main()
