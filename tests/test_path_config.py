import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class PathConfigTests(unittest.TestCase):
    def test_creates_missing_defaults_without_overwriting_user_files(self):
        module = Path(__file__).resolve().parents[1] / "path_config.py"
        templates = module.parent / "setup" / "config_templates"
        with TemporaryDirectory() as temp, patch.object(Path, "home", return_value=Path(temp)):
            runpy.run_path(str(module))
            config = Path(temp) / "MAVRS_settings"
            for name in ("settings.yaml", "pi_addresses.txt", "experiment_names.txt"):
                self.assertEqual((config / name).read_bytes(), (templates / name).read_bytes())
            self.assertTrue((config / "logs").is_dir())
            self.assertTrue((config / "pi_settings").is_dir())
            self.assertTrue((Path(temp) / "MAVRS_data").is_dir())

            (config / "settings.yaml").write_text("custom settings")
            (config / "pi_addresses.txt").unlink()
            runpy.run_path(str(module))
            self.assertEqual((config / "settings.yaml").read_text(), "custom settings")
            self.assertEqual((config / "pi_addresses.txt").read_bytes(),
                             (templates / "pi_addresses.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
