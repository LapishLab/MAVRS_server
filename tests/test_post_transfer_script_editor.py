import unittest
from unittest.mock import patch

from PySide6 import QtWidgets

from user_gui import AutomatedDataProcessingDialog


class PostTransferScriptEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_reorders_scripts_and_arguments_before_saving(self) -> None:
        with patch("user_gui.read_transfer_on_stop", return_value=True), patch(
            "user_gui.read_repair_videos_on_transfer", return_value=False
        ), patch("user_gui.read_post_session_scripts", return_value={
            "First": ["first-tool", "one", "two"],
            "Second": ["second-tool", "{local_data_directory}"],
        }), patch("user_gui.save_processing_preferences") as save:
            dialog = AutomatedDataProcessingDialog()
            first, second = dialog.scripts
            first.arguments[2][0].findChildren(QtWidgets.QToolButton)[0].click()
            self.assertEqual([entry[2].text() for entry in first.arguments], ["Arg1", "Arg2", "Arg3"])
            second.move_up_button.click()
            dialog.btn_save.click()

        save.assert_called_once_with(True, False, post_session_scripts={
            "Second": ["second-tool", "{local_data_directory}"],
            "First": ["first-tool", "two", "one"],
        })
        dialog.deleteLater()

    def test_adds_script_with_separate_arguments(self) -> None:
        with patch("user_gui.read_transfer_on_stop", return_value=True), patch(
            "user_gui.read_repair_videos_on_transfer", return_value=True
        ), patch("user_gui.read_post_session_scripts", return_value={}), patch(
            "user_gui.save_processing_preferences"
        ) as save:
            dialog = AutomatedDataProcessingDialog()
            dialog.btn_add_script.click()
            script = dialog.scripts[0]
            self.assertEqual(script.name.text(), "Script_1")
            argument_arrow = script.arguments[0][0].findChildren(QtWidgets.QToolButton)[0]
            self.assertGreater(script.move_up_button.width(), argument_arrow.width())
            self.assertGreater(script.remove_button.font().pointSize(), argument_arrow.font().pointSize())
            self.assertGreater(dialog.btn_add_script.width(), script.add_argument_button.width())
            script.name.setText("Med")
            self.assertEqual(script.arguments[0][2].text(), "Arg1")
            script.arguments[0][1].setText("C:/Program Files/Python/python.exe")
            script.add_argument_button.click()
            script.arguments[1][1].setText("handling.py")
            script.add_argument_button.click()
            script.arguments[2][1].setText("{local_data_directory}")
            dialog.btn_save.click()

        save.assert_called_once_with(True, True, post_session_scripts={
            "Med": ["C:/Program Files/Python/python.exe", "handling.py", "{local_data_directory}"],
        })
        dialog.deleteLater()

    def test_new_scripts_get_sequential_default_names(self) -> None:
        with patch("user_gui.read_transfer_on_stop", return_value=True), patch(
            "user_gui.read_repair_videos_on_transfer", return_value=True
        ), patch("user_gui.read_post_session_scripts", return_value={"Script_1": ["tool"]}):
            dialog = AutomatedDataProcessingDialog()
            dialog.btn_add_script.click()
            dialog.btn_add_script.click()

        self.assertEqual([script.name.text() for script in dialog.scripts], ["Script_1", "Script_2", "Script_3"])
        dialog.deleteLater()

    def test_first_argument_can_be_removed(self) -> None:
        with patch("user_gui.read_transfer_on_stop", return_value=True), patch(
            "user_gui.read_repair_videos_on_transfer", return_value=True
        ), patch("user_gui.read_post_session_scripts", return_value={
            "Script_1": ["old-tool", "new-tool", "--flag"]
        }), patch("user_gui.save_processing_preferences") as save:
            dialog = AutomatedDataProcessingDialog()
            script = dialog.scripts[0]
            script.arguments[0][0].findChildren(QtWidgets.QToolButton)[2].click()
            self.assertEqual([entry[2].text() for entry in script.arguments], ["Arg1", "Arg2"])
            dialog.btn_save.click()

        save.assert_called_once_with(True, True, post_session_scripts={
            "Script_1": ["new-tool", "--flag"],
        })
        dialog.deleteLater()

    def test_removing_last_script_saves_empty_mapping(self) -> None:
        with patch("user_gui.read_transfer_on_stop", return_value=True), patch(
            "user_gui.read_repair_videos_on_transfer", return_value=True
        ), patch("user_gui.read_post_session_scripts", return_value={"Old": ["tool"]}), patch(
            "user_gui.save_processing_preferences"
        ) as save:
            dialog = AutomatedDataProcessingDialog()
            dialog.scripts[0].remove_button.click()
            dialog.btn_save.click()

        save.assert_called_once_with(True, True, post_session_scripts={})
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
