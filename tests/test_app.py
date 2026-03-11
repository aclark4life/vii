"""Tests for the main vii application."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from textual.widgets import DirectoryTree

from vii.app import Vii, main


class TestVii:
    """Test cases for the Vii class."""

    def test_init_with_default_path(self):
        """Test initialization with default path."""
        app = Vii()
        assert app.start_path == Path.cwd()
        assert isinstance(app.editor_command, list)
        assert len(app.editor_command) > 0

    def test_init_with_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        app = Vii(start_path=tmp_path)
        assert app.start_path == tmp_path

    @patch.dict(os.environ, {"VISUAL": "vim"})
    def test_detect_editor_visual_env(self):
        """Test editor detection using VISUAL environment variable."""
        app = Vii()
        assert app.editor_command == ["vim"]

    @patch.dict(os.environ, {"EDITOR": "nano"}, clear=True)
    def test_detect_editor_editor_env(self):
        """Test editor detection using EDITOR environment variable."""
        app = Vii()
        assert app.editor_command == ["nano"]

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_detect_editor_which_code(self, mock_run):
        """Test editor detection using 'which' command for VS Code."""
        # First call to 'which code' succeeds
        mock_run.return_value = Mock(returncode=0)
        app = Vii()
        assert app.editor_command == ["code"]

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_detect_editor_fallback_to_open(self, mock_run):
        """Test editor detection fallback to 'open'."""
        # All 'which' commands fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "which")
        app = Vii()
        assert app.editor_command == ["open"]

    def test_is_terminal_editor_vim(self):
        """Test detection of vim as terminal editor."""
        app = Vii()
        app.editor_command = ["vim"]
        assert app._is_terminal_editor() is True

    def test_is_terminal_editor_nvim(self):
        """Test detection of nvim as terminal editor."""
        app = Vii()
        app.editor_command = ["nvim"]
        assert app._is_terminal_editor() is True

    def test_is_terminal_editor_code(self):
        """Test detection of VS Code as GUI editor."""
        app = Vii()
        app.editor_command = ["code"]
        assert app._is_terminal_editor() is False

    def test_is_terminal_editor_with_path(self):
        """Test detection works with full paths."""
        app = Vii()
        app.editor_command = ["/usr/bin/vim"]
        assert app._is_terminal_editor() is True

    def test_open_in_gui_editor_success(self, tmp_path):
        """Test successfully opening a file in GUI editor."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        app = Vii(start_path=tmp_path)
        app.editor_command = ["test-editor"]
        app.is_terminal_editor = False

        # Mock Popen and notify after app initialization
        with (
            patch("subprocess.Popen") as mock_popen,
            patch.object(app, "notify") as mock_notify,
        ):
            app._open_in_editor(test_file)

            # Verify Popen was called with correct arguments
            mock_popen.assert_called_once_with(
                ["test-editor", str(test_file)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Verify notification was sent
            mock_notify.assert_called_once_with(f"Opened: {test_file.name}", severity="information")

    @patch("subprocess.run")
    def test_open_in_terminal_editor_success(self, mock_run, tmp_path):
        """Test successfully opening a file in terminal editor."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock successful editor run
        mock_run.return_value = Mock(returncode=0)

        app = Vii(start_path=tmp_path)
        app.editor_command = ["vim"]
        app.is_terminal_editor = True

        # Mock the suspend method to avoid actually suspending
        with patch.object(app, "suspend") as mock_suspend:
            mock_suspend.return_value.__enter__ = Mock()
            mock_suspend.return_value.__exit__ = Mock(return_value=False)

            app._open_in_editor(test_file)

            # Verify subprocess.run was called with the file
            # Note: mock_run is called during __init__ for editor detection too
            # So we check the last call
            assert mock_run.call_args == ((["vim", str(test_file)],), {})

    @patch("subprocess.run")
    def test_open_in_terminal_editor_nonzero_exit(self, mock_run, tmp_path):
        """Test terminal editor with non-zero exit code."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock editor run with non-zero exit
        mock_run.return_value = Mock(returncode=1)

        app = Vii(start_path=tmp_path)
        app.editor_command = ["vim"]
        app.is_terminal_editor = True

        with (
            patch.object(app, "suspend") as mock_suspend,
            patch.object(app, "notify") as mock_notify,
        ):
            mock_suspend.return_value.__enter__ = Mock()
            mock_suspend.return_value.__exit__ = Mock(return_value=False)

            app._open_in_editor(test_file)

            # Verify warning notification was sent
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert "exited with code" in call_args[0][0]
            assert call_args[1]["severity"] == "warning"

    def test_open_in_gui_editor_failure(self, tmp_path):
        """Test handling of GUI editor opening failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        app = Vii(start_path=tmp_path)
        app.editor_command = ["nonexistent-editor"]
        app.is_terminal_editor = False

        # Mock Popen to raise an exception and notify after app initialization
        with (
            patch("subprocess.Popen") as mock_popen,
            patch.object(app, "notify") as mock_notify,
        ):
            # Make Popen raise an exception
            mock_popen.side_effect = OSError("Editor not found")

            app._open_in_editor(test_file)

            # Verify error notification was sent
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert "Error opening file" in call_args[0][0]
            assert call_args[1]["severity"] == "error"

    async def test_compose(self, tmp_path):
        """Test UI composition."""
        app = Vii(start_path=tmp_path)
        async with app.run_test():
            # Check that the directory tree is present
            tree = app.query_one(DirectoryTree)
            assert tree is not None

            # Check that the static info text is present
            from textual.widgets import Static

            statics = app.query(Static)
            # Should have at least one Static widget with our info text
            assert len(statics) > 0
            # Find the one with our text (looking for the navigation hint text)
            found_info_text = False
            for static in statics:
                if hasattr(static, "render") and "Navigate with j/k" in str(static.render()):
                    found_info_text = True
                    break
            assert found_info_text

    async def test_file_selection(self, tmp_path):
        """Test file selection updates content and keeps focus in sidebar."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            # Simulate file selection
            tree = app.query_one(DirectoryTree)
            event = DirectoryTree.FileSelected(tree, test_file)
            app.on_directory_tree_file_selected(event)

            # Allow the focus change to be processed
            await pilot.pause()

            # Verify sidebar keeps focus (file selection no longer switches to content panel)
            assert tree.has_focus


class TestMain:
    """Test cases for the main entry point."""

    @patch("vii.app.Vii")
    def test_main_default_path(self, mock_vii_class):
        """Test main function with default path."""
        mock_app = Mock()
        mock_vii_class.return_value = mock_app

        with patch("sys.argv", ["vii"]):
            main()

        mock_vii_class.assert_called_once()
        call_args = mock_vii_class.call_args
        assert call_args[1]["start_path"] == Path.cwd()
        mock_app.run.assert_called_once()

    @patch("vii.app.Vii")
    def test_main_custom_path(self, mock_vii_class, tmp_path):
        """Test main function with custom path."""
        mock_app = Mock()
        mock_vii_class.return_value = mock_app

        with patch("sys.argv", ["vii", str(tmp_path)]):
            main()

        mock_vii_class.assert_called_once()
        call_args = mock_vii_class.call_args
        assert call_args[1]["start_path"] == tmp_path
        mock_app.run.assert_called_once()

    def test_main_nonexistent_path(self, capsys):
        """Test main function with nonexistent path."""
        with patch("sys.argv", ["vii", "/nonexistent/path"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "does not exist" in captured.err
