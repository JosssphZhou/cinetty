"""Check the installation contract against the installed pinned distributions."""
import importlib.metadata as metadata
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent


class PythonVersion(unittest.TestCase):
    def test_declared_python_supports_every_pinned_package(self):
        declared = (ROOT / ".python-version").read_text().strip()
        for line in (ROOT / "requirements.txt").read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            name, version = line.split("==")
            with self.subTest(package=name):
                installed = metadata.distribution(name)
                self.assertEqual(installed.version, version)
                requirement = installed.metadata.get("Requires-Python")
                self.assertIsNotNone(requirement, name)
                # The light pins all declare a single minimum Python version.
                # Fail explicitly if a future pin needs a more complex rule.
                minimum = re.fullmatch(r">=(\d+)\.(\d+)(?:\.(\d+))?", requirement)
                self.assertIsNotNone(minimum, f"unsupported Requires-Python: {requirement}")
                self.assertGreaterEqual(tuple(map(int, declared.split("."))) + (0,),
                                        tuple(int(v or 0) for v in minimum.groups()),
                                        f"{name}=={version} requires Python {requirement}")

    def test_readme_and_setup_use_the_declared_python(self):
        declared = (ROOT / ".python-version").read_text().strip()
        versions = re.findall(r"Python (\d+\.\d+)", (ROOT / "README.md").read_text())
        self.assertTrue(versions)
        self.assertEqual(set(versions), {declared})
        setup = (ROOT / "scripts/setup.sh").read_text()
        lib = (ROOT / "scripts/lib.sh").read_text()
        self.assertIn('MIN_PYTHON=$(cat "$ROOT/.python-version")', lib)
        self.assertIn('PYTHON_VERSION=${PYTHON_VERSION:-$MIN_PYTHON}', setup)
        self.assertIn('version_ok "$PY"', setup)
        self.assertIn('"$MIN_PYTHON"', setup)

    def test_setup_keeps_uv_downloads_in_the_repository(self):
        setup = (ROOT / "scripts/setup.sh").read_text()
        for variable in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR"):
            with self.subTest(variable=variable):
                self.assertRegex(setup, rf'export {variable}="\$ROOT/\.setup-cache/[^".]+"')
        self.assertIn(".setup-cache/", (ROOT / ".gitignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
