"""Tests for the main vii application."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from textual.widgets import DirectoryTree

from vii.app import Vii, main
from vii.config import Config, get_config_dir, get_config_path


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
    @patch("vii.app.get_git_root")
    @patch("vii.app.is_git_repo")
    @patch("subprocess.run")
    def test_detect_editor_which_code(self, mock_run, mock_is_git_repo, mock_get_git_root):
        """Test editor detection using 'which' command for VS Code."""
        # Mock git functions to avoid git-related calls
        mock_is_git_repo.return_value = False
        mock_get_git_root.return_value = None
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

    @patch("vii.app.get_git_root")
    @patch("vii.app.is_git_repo")
    @patch("subprocess.run")
    def test_open_in_terminal_editor_success(
        self, mock_run, mock_is_git_repo, mock_get_git_root, tmp_path
    ):
        """Test successfully opening a file in terminal editor."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock git functions to avoid git-related calls
        mock_is_git_repo.return_value = False
        mock_get_git_root.return_value = None
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
        async with app.run_test() as pilot:
            await pilot.pause()  # Allow widgets to mount
            # Check that the directory tree is present
            # Walk through all descendants to find the DirectoryTree
            tree = None
            for widget in app.walk_children():
                if isinstance(widget, DirectoryTree):
                    tree = widget
                    break
            assert tree is not None

            # Check that the static info text is present
            from textual.widgets import Static

            # Walk through all descendants to find Static widgets
            statics = [w for w in app.walk_children() if isinstance(w, Static)]
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
            await pilot.pause()  # Allow widgets to mount
            # Simulate file selection - walk children to find tree
            tree = None
            for widget in app.walk_children():
                if isinstance(widget, DirectoryTree):
                    tree = widget
                    break
            assert tree is not None
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


class TestConfig:
    """Test cases for the Config class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        assert config.theme == "textual-dark"
        assert config.sidebar_width is None
        assert config.animate_scroll is True

    def test_config_from_dict(self):
        """Test creating config from a dictionary."""
        data = {"theme": "monokai", "sidebar_width": 40, "animate_scroll": False}
        config = Config.from_dict(data)
        assert config.theme == "monokai"
        assert config.sidebar_width == 40
        assert config.animate_scroll is False

    def test_config_from_dict_partial(self):
        """Test creating config from partial dictionary."""
        data = {"theme": "dracula"}
        config = Config.from_dict(data)
        assert config.theme == "dracula"
        assert config.sidebar_width is None

    def test_config_from_dict_empty(self):
        """Test creating config from empty dictionary uses defaults."""
        config = Config.from_dict({})
        assert config.theme == "textual-dark"
        assert config.sidebar_width is None

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = Config(theme="nord", sidebar_width=35, animate_scroll=False)
        data = config.to_dict()
        assert data["theme"] == "nord"
        assert data["sidebar_width"] == 35
        assert data["animate_scroll"] is False

    def test_config_to_dict_no_sidebar_width(self):
        """Test that None sidebar_width is excluded from dict."""
        config = Config(theme="nord", sidebar_width=None)
        data = config.to_dict()
        assert data["theme"] == "nord"
        assert "sidebar_width" not in data

    def test_config_save_and_load(self, tmp_path, monkeypatch):
        """Test saving and loading config."""
        # Use a temporary config directory
        config_dir = tmp_path / ".config" / "vii"
        monkeypatch.setattr("vii.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("vii.config.get_config_path", lambda: config_dir / "config.toml")

        # Save config
        config = Config(theme="gruvbox", sidebar_width=50)
        config.save()

        # Verify file was created
        config_path = config_dir / "config.toml"
        assert config_path.exists()

        # Load config
        loaded = Config.load()
        assert loaded.theme == "gruvbox"
        assert loaded.sidebar_width == 50

    def test_config_load_missing_file(self, tmp_path, monkeypatch):
        """Test loading config when file doesn't exist returns defaults."""
        config_dir = tmp_path / ".config" / "vii"
        monkeypatch.setattr("vii.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("vii.config.get_config_path", lambda: config_dir / "config.toml")

        config = Config.load()
        assert config.theme == "textual-dark"
        assert config.sidebar_width is None

    def test_config_load_invalid_file(self, tmp_path, monkeypatch):
        """Test loading config with invalid TOML returns defaults."""
        config_dir = tmp_path / ".config" / "vii"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text("invalid toml [[[")

        monkeypatch.setattr("vii.config.get_config_dir", lambda: config_dir)
        monkeypatch.setattr("vii.config.get_config_path", lambda: config_path)

        config = Config.load()
        assert config.theme == "textual-dark"
        assert config.sidebar_width is None

    def test_get_config_dir(self):
        """Test config directory path."""
        config_dir = get_config_dir()
        assert config_dir == Path.home() / ".config" / "vii"

    def test_get_config_path(self):
        """Test config file path."""
        config_path = get_config_path()
        assert config_path == Path.home() / ".config" / "vii" / "config.toml"
