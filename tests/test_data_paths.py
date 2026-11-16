import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from data_paths import read_data_paths, save_data_paths


class DataPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        temporary = TemporaryDirectory(dir=repository)
        self.assertTrue(Path(temporary.name).resolve().is_relative_to(repository.resolve()))
        self.addCleanup(temporary.cleanup)
        self.settings_file = Path(temporary.name) / "settings.yaml"

    def test_save_preserves_unrelated_setting_values(self) -> None:
        self.settings_file.write_text(
            'local_data_path: "C:/old/" # local note\n'
            'backup_data_path: "user@old:/backup/"\n'
            'other_folders:\n'
            '  ephys:\n'
            '  med_pc: "user@old:/data/"\n'
            'suggested_name_format: "%date%_%experiment%" # keep this\n'
            'custom_setting:\n'
            '  enabled: true\n',
            encoding="utf-8",
        )

        save_data_paths(
            "C:/new/#data/", None,
            {"ephys": None, "med_pc": "user@new:/data/#session", "extra": "D:/more/"},
            self.settings_file,
        )

        self.assertEqual(
            read_data_paths(self.settings_file),
            ("C:/new/#data/", None, {"ephys": None, "med_pc": "user@new:/data/#session", "extra": "D:/more/"}),
        )
        saved = yaml.safe_load(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["suggested_name_format"], "%date%_%experiment%")
        self.assertEqual(saved["custom_setting"], {"enabled": True})
        self.assertNotIn("# local note", self.settings_file.read_text(encoding="utf-8"))

    def test_save_can_add_missing_folder_setting_and_remove_all_rows(self) -> None:
        self.settings_file.write_text(
            'local_data_path: "/old/"\nbackup_data_path: null\nsuggested_name_format: "%date%"\n',
            encoding="utf-8",
        )

        save_data_paths("/new/", "user@host:/backup/", {}, self.settings_file)

        self.assertEqual(read_data_paths(self.settings_file), ("/new/", "user@host:/backup/", {}))
        self.assertEqual(yaml.safe_load(self.settings_file.read_text())["other_folders"], {})

    def test_invalid_yaml_is_not_overwritten(self) -> None:
        original = "local_data_path: [broken\n"
        self.settings_file.write_text(original, encoding="utf-8")

        with self.assertRaises(yaml.YAMLError):
            save_data_paths("/new/", None, {}, self.settings_file)

        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), original)

if __name__ == "__main__":
    unittest.main()
