import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from gui_settings import (
    read_data_paths, read_repair_videos_on_transfer, read_transfer_on_stop,
    save_data_paths, save_processing_preferences,
)


class DataPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        temporary = TemporaryDirectory(dir=repository)
        self.assertTrue(Path(temporary.name).resolve().is_relative_to(repository.resolve()))
        self.addCleanup(temporary.cleanup)
        self.settings_file = Path(temporary.name) / "settings.yaml"

    def test_processing_preferences_save_together_and_migrate_old_repair_key(self) -> None:
        local = "C:/data/" if os.name == "nt" else "/data/"
        self.settings_file.write_text(
            yaml.safe_dump({
                "local_data_path": local,
                "backup_data_path": None,
                "repair_videos_on_stop": False,
            }),
            encoding="utf-8",
        )
        self.assertTrue(read_transfer_on_stop(self.settings_file))
        self.assertFalse(read_repair_videos_on_transfer(self.settings_file))

        save_processing_preferences(False, True, self.settings_file)

        self.assertFalse(read_transfer_on_stop(self.settings_file))
        self.assertTrue(read_repair_videos_on_transfer(self.settings_file))
        saved = yaml.safe_load(self.settings_file.read_text(encoding="utf-8"))
        self.assertNotIn("repair_videos_on_stop", saved)

    def test_save_preserves_unrelated_setting_values(self) -> None:
        old_local = "C:/old/" if os.name == "nt" else "/old/"
        new_local = "C:/new/#data/" if os.name == "nt" else "/new/#data/"
        extra_path = "D:/more/" if os.name == "nt" else "/more/"
        self.settings_file.write_text(
            f'local_data_path: "{old_local}" # local note\n'
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
            new_local, None,
            {"ephys": None, "med_pc": "user@new:/data/#session", "extra": extra_path},
            "%time%_%experiment%",
            self.settings_file,
        )

        self.assertEqual(
            read_data_paths(self.settings_file),
            (
                new_local,
                None,
                {"ephys": None, "med_pc": "user@new:/data/#session", "extra": extra_path},
                "%time%_%experiment%",
            ),
        )
        saved = yaml.safe_load(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["suggested_name_format"], "%time%_%experiment%")
        self.assertEqual(saved["custom_setting"], {"enabled": True})
        self.assertNotIn("# local note", self.settings_file.read_text(encoding="utf-8"))

    def test_save_can_add_missing_folder_setting_and_remove_all_rows(self) -> None:
        old_local = "C:/old/" if os.name == "nt" else "/old/"
        new_local = "C:/new/" if os.name == "nt" else "/new/"
        self.settings_file.write_text(
            f'local_data_path: "{old_local}"\nbackup_data_path: null\nsuggested_name_format: "%date%"\n',
            encoding="utf-8",
        )

        save_data_paths(new_local, "user@host:/backup/", {}, "%date%", self.settings_file)

        self.assertEqual(read_data_paths(self.settings_file), (new_local, "user@host:/backup/", {}, "%date%"))
        self.assertEqual(yaml.safe_load(self.settings_file.read_text())["other_folders"], {})

    def test_read_uses_default_name_format_when_setting_is_missing(self) -> None:
        local = "C:/data/" if os.name == "nt" else "/data/"
        self.settings_file.write_text(
            yaml.safe_dump({"local_data_path": local, "backup_data_path": None, "other_folders": {}}),
            encoding="utf-8",
        )

        _, _, _, suggested_name_format = read_data_paths(self.settings_file)

        self.assertEqual(suggested_name_format, "%date%_%time%_%experiment%_rat%input{rat number}%")

    def test_invalid_paths_are_not_saved(self) -> None:
        local = "C:/data/" if os.name == "nt" else "/data/"
        self.settings_file.write_text(
            yaml.safe_dump({"local_data_path": local, "backup_data_path": None, "other_folders": {}}),
            encoding="utf-8",
        )
        original = self.settings_file.read_text(encoding="utf-8")

        for local_path, backup_path, folders in (
            ("user@host:/remote/", None, {}),
            (local, "user@host:", {}),
            (local, None, {"ephys": "relative/folder"}),
        ):
            with self.subTest(local_path=local_path, backup_path=backup_path, folders=folders):
                with self.assertRaises(ValueError):
                    save_data_paths(local_path, backup_path, folders, "%date%", self.settings_file)
                self.assertEqual(self.settings_file.read_text(encoding="utf-8"), original)

    def test_validation_messages_identify_fields_and_folder(self) -> None:
        from pydantic import ValidationError
        from load_settings import Settings
        from user_gui import format_settings_validation_errors

        with self.assertRaises(ValidationError) as caught:
            Settings.model_validate({
                "local_data_path": "user@host:/remote/",
                "backup_data_path": "user@host:",
                "other_folders": {"ephys": "relative/folder"},
            })

        message = format_settings_validation_errors(caught.exception)
        self.assertIn("Local data path: must be a local directory", message)
        self.assertIn("Backup data path: requires a directory path", message)
        self.assertIn("Other folders: Folder 'ephys':", message)

    def test_invalid_yaml_is_not_overwritten(self) -> None:
        original = "local_data_path: [broken\n"
        self.settings_file.write_text(original, encoding="utf-8")

        with self.assertRaises(yaml.YAMLError):
            save_data_paths("/new/", None, {}, "%date%", self.settings_file)

        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), original)

if __name__ == "__main__":
    unittest.main()
