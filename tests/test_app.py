"""Tests for the main Tide application."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from textual.widgets import DirectoryTree

from tide.app import TideIDE, main


class TestTideIDE:
    """Test cases for the TideIDE class."""

    def test_init_with_default_path(self):
        """Test initialization with default path."""
        app = TideIDE()
        assert app.start_path == Path.cwd()
        assert isinstance(app.editor_command, list)
        assert len(app.editor_command) > 0

    def test_init_with_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        app = TideIDE(start_path=tmp_path)
        assert app.start_path == tmp_path

    @patch.dict(os.environ, {"VISUAL": "vim"})
    def test_detect_editor_visual_env(self):
        """Test editor detection using VISUAL environment variable."""
        app = TideIDE()
        assert app.editor_command == ["vim"]

    @patch.dict(os.environ, {"EDITOR": "nano"}, clear=True)
    def test_detect_editor_editor_env(self):
        """Test editor detection using EDITOR environment variable."""
        app = TideIDE()
        assert app.editor_command == ["nano"]

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_detect_editor_which_code(self, mock_run):
        """Test editor detection using 'which' command for VS Code."""
        # First call to 'which code' succeeds
        mock_run.return_value = Mock(returncode=0)
        app = TideIDE()
        assert app.editor_command == ["code"]

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_detect_editor_fallback_to_open(self, mock_run):
        """Test editor detection fallback to 'open'."""
        # All 'which' commands fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "which")
        app = TideIDE()
        assert app.editor_command == ["open"]

    def test_is_terminal_editor_vim(self):
        """Test detection of vim as terminal editor."""
        app = TideIDE()
        app.editor_command = ["vim"]
        assert app._is_terminal_editor() is True

    def test_is_terminal_editor_nvim(self):
        """Test detection of nvim as terminal editor."""
        app = TideIDE()
        app.editor_command = ["nvim"]
        assert app._is_terminal_editor() is True

    def test_is_terminal_editor_code(self):
        """Test detection of VS Code as GUI editor."""
        app = TideIDE()
        app.editor_command = ["code"]
        assert app._is_terminal_editor() is False

    def test_is_terminal_editor_with_path(self):
        """Test detection works with full paths."""
        app = TideIDE()
        app.editor_command = ["/usr/bin/vim"]
        assert app._is_terminal_editor() is True

    @patch("subprocess.Popen")
    def test_open_in_gui_editor_success(self, mock_popen, tmp_path):
        """Test successfully opening a file in GUI editor."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        app = TideIDE(start_path=tmp_path)
        app.editor_command = ["test-editor"]
        app.is_terminal_editor = False

        # Mock the notify method
        app.notify = Mock()

        app._open_in_editor(test_file)

        # Verify Popen was called with correct arguments
        mock_popen.assert_called_once_with(
            ["test-editor", str(test_file)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Verify notification was sent
        app.notify.assert_called_once_with(
            f"Opened: {test_file.name}", severity="information"
        )

    @patch("subprocess.run")
    def test_open_in_terminal_editor_success(self, mock_run, tmp_path):
        """Test successfully opening a file in terminal editor."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock successful editor run
        mock_run.return_value = Mock(returncode=0)

        app = TideIDE(start_path=tmp_path)
        app.editor_command = ["vim"]
        app.is_terminal_editor = True

        # Mock the notify method and suspend context
        app.notify = Mock()

        # Mock the suspend method to avoid actually suspending
        with patch.object(app, "suspend") as mock_suspend:
            mock_suspend.return_value.__enter__ = Mock()
            mock_suspend.return_value.__exit__ = Mock(return_value=False)

            app._open_in_editor(test_file)

            # Verify subprocess.run was called
            mock_run.assert_called_once_with(
                ["vim", str(test_file)],
            )

    @patch("subprocess.run")
    def test_open_in_terminal_editor_nonzero_exit(self, mock_run, tmp_path):
        """Test terminal editor with non-zero exit code."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock editor run with non-zero exit
        mock_run.return_value = Mock(returncode=1)

        app = TideIDE(start_path=tmp_path)
        app.editor_command = ["vim"]
        app.is_terminal_editor = True
        app.notify = Mock()

        with patch.object(app, "suspend") as mock_suspend:
            mock_suspend.return_value.__enter__ = Mock()
            mock_suspend.return_value.__exit__ = Mock(return_value=False)

            app._open_in_editor(test_file)

            # Verify warning notification was sent
            app.notify.assert_called_once()
            call_args = app.notify.call_args
            assert "exited with code" in call_args[0][0]
            assert call_args[1]["severity"] == "warning"

    @patch("subprocess.Popen")
    def test_open_in_gui_editor_failure(self, mock_popen, tmp_path):
        """Test handling of GUI editor opening failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Make Popen raise an exception
        mock_popen.side_effect = OSError("Editor not found")

        app = TideIDE(start_path=tmp_path)
        app.editor_command = ["nonexistent-editor"]
        app.is_terminal_editor = False

        # Mock the notify method
        app.notify = Mock()

        app._open_in_editor(test_file)

        # Verify error notification was sent
        app.notify.assert_called_once()
        call_args = app.notify.call_args
        assert "Error opening file" in call_args[0][0]
        assert call_args[1]["severity"] == "error"

    async def test_compose(self, tmp_path):
        """Test UI composition."""
        app = TideIDE(start_path=tmp_path)
        async with app.run_test():
            # Check that the directory tree is present
            tree = app.query_one(DirectoryTree)
            assert tree is not None

            # Check that the static info text is present
            from textual.widgets import Static

            statics = app.query(Static)
            # Should have at least one Static widget with our info text
            assert len(statics) > 0
            # Find the one with our text
            found_info_text = False
            for static in statics:
                if hasattr(static, "render") and "Select a file" in str(
                    static.render()
                ):
                    found_info_text = True
                    break
            assert found_info_text

    async def test_file_selection(self, tmp_path):
        """Test file selection triggers editor opening."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        app = TideIDE(start_path=tmp_path)

        with patch.object(app, "_open_in_editor") as mock_open:
            async with app.run_test():
                # Simulate file selection
                tree = app.query_one(DirectoryTree)
                event = DirectoryTree.FileSelected(tree, test_file)
                app.on_directory_tree_file_selected(event)

                # Verify _open_in_editor was called
                mock_open.assert_called_once_with(test_file)


class TestMain:
    """Test cases for the main entry point."""

    @patch("tide.app.TideIDE")
    def test_main_default_path(self, mock_tide_class):
        """Test main function with default path."""
        mock_app = Mock()
        mock_tide_class.return_value = mock_app

        with patch("sys.argv", ["tide"]):
            main()

        mock_tide_class.assert_called_once()
        call_args = mock_tide_class.call_args
        assert call_args[1]["start_path"] == Path.cwd()
        mock_app.run.assert_called_once()

    @patch("tide.app.TideIDE")
    def test_main_custom_path(self, mock_tide_class, tmp_path):
        """Test main function with custom path."""
        mock_app = Mock()
        mock_tide_class.return_value = mock_app

        with patch("sys.argv", ["tide", str(tmp_path)]):
            main()

        mock_tide_class.assert_called_once()
        call_args = mock_tide_class.call_args
        assert call_args[1]["start_path"] == tmp_path
        mock_app.run.assert_called_once()

    def test_main_nonexistent_path(self, capsys):
        """Test main function with nonexistent path."""
        with patch("sys.argv", ["tide", "/nonexistent/path"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert "does not exist" in captured.err
