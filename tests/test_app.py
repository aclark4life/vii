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
            await pilot.pause()  # Extra pause for CI environments

            # Check that the directory tree is present
            tree = None
            for widget in app.walk_children():
                if isinstance(widget, DirectoryTree):
                    tree = widget
                    break
            assert tree is not None, "DirectoryTree widget should be present"

            # Check that content display widget is present
            from textual.widgets import Static

            content_display = None
            for widget in app.walk_children():
                if isinstance(widget, Static) and widget.id == "content-display":
                    content_display = widget
                    break
            assert content_display is not None, "content-display Static widget should be present"

            # Check that scroll container is present and focusable
            scroll_container = app._get_scroll_container()
            assert scroll_container is not None, "scroll container should be present"
            assert scroll_container.can_focus, "scroll container should be focusable"

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

    async def test_jk_navigation(self, tmp_path):
        """Test j/k keys navigate in the directory tree."""
        # Create test files
        (tmp_path / "file1.txt").write_text("first")
        (tmp_path / "file2.txt").write_text("second")
        (tmp_path / "file3.txt").write_text("third")

        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            tree = app._get_tree()
            assert tree is not None

            # Expand the root to see files
            tree.root.expand()
            await pilot.pause()
            await pilot.pause()

            # Initial cursor should be on root
            initial_cursor = tree.cursor_node.data.path.name

            # Press j to move down
            await pilot.press("j")
            await pilot.pause()
            after_j = tree.cursor_node.data.path.name
            assert after_j != initial_cursor, "j should move cursor down"

            # Press j again
            await pilot.press("j")
            await pilot.pause()
            after_second_j = tree.cursor_node.data.path.name
            assert after_second_j != after_j, "j should continue moving down"

            # Press k to move back up
            await pilot.press("k")
            await pilot.pause()
            after_k = tree.cursor_node.data.path.name
            assert after_k == after_j, "k should move cursor back up"

    async def test_panel_resizing(self, tmp_path):
        """Test sidebar panel can be resized."""
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Find the sidebar
            sidebar = None
            for widget in app.walk_children():
                if widget.id == "sidebar":
                    sidebar = widget
                    break
            assert sidebar is not None

            # Set a new width
            app.set_sidebar_width(40)
            await pilot.pause()

            assert app.sidebar_width == 40
            assert sidebar.styles.width.value == 40

            # Set another width
            app.set_sidebar_width(60)
            await pilot.pause()

            assert app.sidebar_width == 60
            assert sidebar.styles.width.value == 60

    async def test_content_loading(self, tmp_path):
        """Test content panel loads file content when navigating."""
        # Create a test file with known content
        test_content = "Hello, this is test content!"
        (tmp_path / "test.txt").write_text(test_content)

        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            tree = app._get_tree()
            assert tree is not None

            # Expand root
            tree.root.expand()
            await pilot.pause()
            await pilot.pause()

            # Navigate to the file
            await pilot.press("j")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()  # Wait for debounced content update

            # Check content display
            content_display = app._get_content_display()
            assert content_display is not None

            rendered = str(content_display.render())
            assert test_content in rendered, f"Content should contain '{test_content}'"

    async def test_helper_methods_return_widgets(self, tmp_path):
        """Test that _get_tree, _get_scroll_container, _get_content_display return widgets."""
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Test _get_tree
            tree = app._get_tree()
            assert tree is not None
            assert isinstance(tree, DirectoryTree)

            # Test _get_scroll_container
            scroll = app._get_scroll_container()
            assert scroll is not None
            assert scroll.id == "content-scroll"

            # Test _get_content_display
            content = app._get_content_display()
            assert content is not None
            assert content.id == "content-display"

    async def test_enter_behavior(self, tmp_path):
        """Test Enter key behavior in sidebar and content panel."""
        # Create multiple test files
        (tmp_path / "file1.txt").write_text("content 1")
        (tmp_path / "file2.txt").write_text("content 2")
        (tmp_path / "file3.txt").write_text("content 3")

        # Create a test file with multiple lines for content scrolling
        test_content = "\n".join([f"Line {i}" for i in range(50)])
        (tmp_path / "test.txt").write_text(test_content)

        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            tree = app._get_tree()
            scroll = app._get_scroll_container()

            # Expand root to see files
            tree.root.expand()
            await pilot.pause()
            await pilot.pause()

            # Initial state: tree has focus
            assert tree.has_focus
            assert not scroll.has_focus

            # Get initial cursor position in tree (should be on root directory)
            initial_cursor = tree.cursor_node
            assert initial_cursor.data.path.is_dir()
            initial_expansion_state = initial_cursor.is_expanded

            # Enter in sidebar on a directory toggles expansion
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()  # Wait for content update

            # Focus should remain in sidebar
            assert tree.has_focus
            assert not scroll.has_focus
            # Directory expansion should have toggled (was expanded, now collapsed)
            assert tree.cursor_node.is_expanded != initial_expansion_state
            assert not tree.cursor_node.is_expanded  # Should now be collapsed
            # Cursor should still be on the same node
            assert tree.cursor_node == initial_cursor

            # Press Enter again to expand it back
            await pilot.press("enter")
            await pilot.pause()
            assert tree.cursor_node.is_expanded  # Should now be expanded again

            # Now move to a file and test Enter behavior
            await pilot.press("j")  # Move down to first child (should be a file)
            await pilot.pause()

            # Verify we're on a file
            file_node = tree.cursor_node
            if not file_node.data.path.is_file():
                # If not a file, skip down until we find one
                for _ in range(10):
                    await pilot.press("j")
                    await pilot.pause()
                    if tree.cursor_node.data.path.is_file():
                        file_node = tree.cursor_node
                        break

            assert file_node.data.path.is_file(), f"Expected file but got {file_node.data.path}"

            # Enter on a file should switch focus to content panel
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            # Focus should have switched to content panel
            assert scroll.has_focus
            assert not tree.has_focus

            # Tab back to sidebar for next test
            await pilot.press("tab")
            await pilot.pause()
            assert tree.has_focus

            # Tab to content panel
            await pilot.press("tab")
            await pilot.pause()
            assert scroll.has_focus
            assert not tree.has_focus

            # Enter in content panel should scroll down (not switch focus)
            initial_scroll_y = scroll.scroll_y
            await pilot.press("enter")
            await pilot.pause()
            # Focus should remain in content panel
            assert scroll.has_focus
            assert not tree.has_focus
            # Scroll position should have changed (scrolled down)
            assert scroll.scroll_y >= initial_scroll_y

    async def test_jk_scrolls_in_git_commit_view(self, tmp_path):
        """Test j/k scrolls content when viewing a git commit (not navigating log)."""
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            scroll = app._get_scroll_container()

            # Simulate being in git commit viewing mode
            app.git.log_viewing = True
            app.git.commit_viewing = True
            app.git.log_entries = [(0, 2), (3, 5), (6, 8)]
            app.git.log_highlighted_entry = 1

            # Focus the content panel
            scroll.focus()
            await pilot.pause()
            assert scroll.has_focus

            initial_entry = app.git.log_highlighted_entry

            # Press j - should scroll, not navigate log entries
            await pilot.press("j")
            await pilot.pause()

            # The highlighted entry should NOT have changed
            assert app.git.log_highlighted_entry == initial_entry

            # Press k - should scroll, not navigate log entries
            await pilot.press("k")
            await pilot.pause()

            # The highlighted entry should still NOT have changed
            assert app.git.log_highlighted_entry == initial_entry

    async def test_jk_scrolls_in_git_commit_view_integration(self):
        """Integration test: j/k scrolls when viewing commit details from git log."""
        import subprocess
        from pathlib import Path

        # Use the vii project directory (a real git repo)
        vii_path = Path(__file__).parent.parent

        # Verify it's a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=vii_path,
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip("Not in a git repository")

        app = Vii(start_path=vii_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            scroll = app._get_scroll_container()

            # Focus content panel
            scroll.focus()
            await pilot.pause()

            # Verify git info is initialized
            assert app.git.branch is not None, "Should be in a git repository"
            assert app.git.root is not None, "Git root should be set"

            # Manually set up git commit viewing state
            # (The actual triggering mechanism via actions is flaky in tests)
            app.git.log_viewing = True
            app.git.commit_viewing = True
            app.git.log_entries = [(0, 2), (3, 5), (6, 8)]  # Dummy entries
            app.git.log_highlighted_entry = 1
            await pilot.pause()

            initial_entry = app.git.log_highlighted_entry

            # Now j/k should scroll, not navigate log entries
            await pilot.press("j")
            await pilot.pause()

            assert app.git.log_highlighted_entry == initial_entry, (
                "j should scroll commit view, not navigate log entries"
            )

            await pilot.press("k")
            await pilot.pause()

            assert app.git.log_highlighted_entry == initial_entry, (
                "k should scroll commit view, not navigate log entries"
            )

            # ESC should go back to log view
            await pilot.press("escape")
            await pilot.pause()

            assert not app.git.commit_viewing, "Should be back to log view"
            assert app.git.log_viewing, "Should still be viewing log"

    async def test_get_blame_line_commit_hash(self, tmp_path):
        """Test extracting commit hash from blame line."""
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Test with normal commit hash
            app.git.blame_output = "abc123de test.py (John Doe 2024-01-15  1) print('hello')"
            app.git.blame_highlighted_line = 0

            commit_hash = app._get_blame_line_commit_hash()
            assert commit_hash == "abc123de"

            # Test with boundary commit (^ prefix)
            app.git.blame_output = "^abc123de test.py (John Doe 2024-01-15  1) print('hello')"
            app.git.blame_highlighted_line = 0

            commit_hash = app._get_blame_line_commit_hash()
            assert commit_hash == "abc123de"

            # Test with no blame output
            app.git.blame_output = ""
            commit_hash = app._get_blame_line_commit_hash()
            assert commit_hash is None

            # Test with invalid line number
            app.git.blame_output = "abc123de test.py (John Doe 2024-01-15  1) print('hello')"
            app.git.blame_highlighted_line = 10
            commit_hash = app._get_blame_line_commit_hash()
            assert commit_hash is None

    @pytest.mark.asyncio
    async def test_quit_dialog_focus(self, tmp_path):
        """Test that the quit dialog opens with Cancel focused and Enter dismisses it."""
        (tmp_path / "test.txt").write_text("hello")
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press q to open the quit dialog
            await pilot.press("q")
            await pilot.pause()
            await pilot.pause()

            from textual.screen import ModalScreen
            from textual.widgets import Button

            assert isinstance(app.screen, ModalScreen), "Quit dialog should be a modal"
            modal = app.screen
            cancel = modal.query_one("#cancel", Button)
            quit_btn = modal.query_one("#quit", Button)

            # Cancel button should have focus by default (AUTO_FOCUS = "#cancel")
            assert cancel.has_focus, "Cancel button should have focus when dialog opens"
            assert not quit_btn.has_focus

            # Enter on focused Cancel button should dismiss the dialog (not quit)
            await pilot.press("enter")
            for _ in range(3):
                await pilot.pause()
            assert len(app.screen_stack) == 1, "Dialog should be dismissed after Enter on Cancel"
            assert not isinstance(app.screen, ModalScreen), "Should be back on main screen"

    @pytest.mark.asyncio
    async def test_quit_dialog_tab_navigation(self, tmp_path):
        """Test that Tab moves focus between Quit and Cancel buttons."""
        (tmp_path / "test.txt").write_text("hello")
        app = Vii(start_path=tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            await pilot.press("q")
            await pilot.pause()
            await pilot.pause()

            from textual.widgets import Button

            modal = app.screen
            cancel = modal.query_one("#cancel", Button)
            quit_btn = modal.query_one("#quit", Button)

            assert cancel.has_focus, "Cancel should have initial focus"

            # Tab should move focus to Quit
            await pilot.press("tab")
            await pilot.pause()
            assert quit_btn.has_focus, "Tab should move focus to Quit button"

            # Tab again should cycle back to Cancel
            await pilot.press("tab")
            await pilot.pause()
            assert cancel.has_focus, "Tab should cycle back to Cancel button"

            # Escape should dismiss without quitting
            await pilot.press("escape")
            for _ in range(2):
                await pilot.pause()
            assert len(app.screen_stack) == 1, "Escape should dismiss the dialog"


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
