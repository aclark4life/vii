"""Performance tests for vii."""

import time
from pathlib import Path

import pytest


class TestFileReadingPerformance:
    """Test file reading performance."""

    @pytest.fixture
    def large_python_file(self, tmp_path: Path) -> Path:
        """Create a large Python file for testing."""
        file_path = tmp_path / "large_file.py"
        # Generate ~1000 lines of Python code
        lines = []
        for i in range(1000):
            lines.append(f"def function_{i}(x: int, y: str) -> bool:")
            lines.append(f'    """Docstring for function {i}."""')
            lines.append(f"    result = x + {i}")
            lines.append('    message = f"Value: {result}"')
            lines.append("    return True")
            lines.append("")
        file_path.write_text("\n".join(lines))
        return file_path

    @pytest.fixture
    def small_file(self, tmp_path: Path) -> Path:
        """Create a small file for testing."""
        file_path = tmp_path / "small_file.py"
        file_path.write_text("print('hello world')\n")
        return file_path

    def test_file_read_time(self, large_python_file: Path) -> None:
        """Test that reading a file from disk is fast."""
        start = time.perf_counter()
        content = large_python_file.read_text()
        elapsed = time.perf_counter() - start

        assert len(content) > 1000  # File was read
        assert elapsed < 0.1, f"File read took {elapsed:.3f}s, should be < 0.1s"
        print(f"\nFile read time: {elapsed * 1000:.2f}ms for {len(content)} chars")

    def test_syntax_highlighting_time(self, large_python_file: Path) -> None:
        """Test that syntax highlighting is reasonably fast."""
        from io import StringIO

        from rich.console import Console
        from rich.syntax import Syntax

        content = large_python_file.read_text()

        start = time.perf_counter()
        syntax = Syntax(
            content,
            "python",
            theme="monokai",
            line_numbers=True,
        )
        # Force full rendering by writing to a console
        console = Console(file=StringIO(), width=120, height=50)
        console.print(syntax)
        elapsed = time.perf_counter() - start

        print(f"\nSyntax highlighting time for {len(content)} chars: {elapsed * 1000:.2f}ms")
        # Syntax highlighting 6000 lines can take a bit of time
        assert elapsed < 3.0, f"Syntax highlighting took {elapsed:.3f}s, should be < 3s"

    def test_multiple_file_reads_with_syntax(self, tmp_path: Path) -> None:
        """Test reading and highlighting multiple files rapidly (simulates navigation)."""
        from io import StringIO

        from rich.console import Console
        from rich.syntax import Syntax

        # Create 20 Python files with content
        files = []
        for i in range(20):
            f = tmp_path / f"file_{i}.py"
            f.write_text(f"# File {i}\ndef func_{i}():\n    print({i})\n    return {i}\n")
            files.append(f)

        times = []
        for f in files:
            start = time.perf_counter()
            content = f.read_text()
            syntax = Syntax(content, "python", theme="monokai", line_numbers=True)
            console = Console(file=StringIO(), width=80, height=30)
            console.print(syntax)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times) * 1000
        max_time = max(times) * 1000
        print(f"\nAverage file render time: {avg_time:.2f}ms per file")
        print(f"Max file render time: {max_time:.2f}ms")
        assert avg_time < 50, f"Average render time {avg_time:.2f}ms should be < 50ms"

    def test_large_file_truncation(self, tmp_path: Path) -> None:
        """Test that very large files are truncated for performance."""
        from vii.content import read_file_content

        # Create a file with 3000 lines
        file_path = tmp_path / "huge_file.py"
        lines = [f"print({i})" for i in range(3000)]
        file_path.write_text("\n".join(lines))

        content = read_file_content(file_path)

        # Should be truncated
        assert "truncated" in content
        assert "3,000 total lines" in content
        # Should only have 2000 actual code lines
        actual_lines = [line for line in content.split("\n") if line.startswith("print(")]
        assert len(actual_lines) == 2000, f"Expected 2000 lines, got {len(actual_lines)}"
        print("\nFile correctly truncated to 2000 lines")

    def test_syntax_highlighting_with_truncation(self, tmp_path: Path) -> None:
        """Test that syntax highlighting on truncated files is fast."""
        from io import StringIO

        from rich.console import Console
        from rich.syntax import Syntax

        from vii.content import read_file_content

        # Create a file with 2000 lines (at the limit)
        file_path = tmp_path / "medium_file.py"
        lines = [f"def func_{i}(): return {i}" for i in range(2000)]
        file_path.write_text("\n".join(lines))

        content = read_file_content(file_path)

        start = time.perf_counter()
        syntax = Syntax(content, "python", theme="monokai", line_numbers=True)
        console = Console(file=StringIO(), width=120, height=50)
        console.print(syntax)
        elapsed = time.perf_counter() - start

        print(f"\nSyntax highlighting 2000 lines: {elapsed * 1000:.2f}ms")
        # Should be under 500ms for a good user experience
        assert elapsed < 0.5, f"Took {elapsed:.3f}s, should be < 0.5s"


class TestGitPerformance:
    """Test git operations performance."""

    def test_git_status_time(self, tmp_path: Path) -> None:
        """Test git status check performance."""
        import subprocess

        from vii.git_utils import get_git_file_status, is_git_repo

        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create some files
        for i in range(10):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")

        start = time.perf_counter()
        is_repo = is_git_repo(tmp_path)
        elapsed_check = time.perf_counter() - start

        start = time.perf_counter()
        _ = get_git_file_status(tmp_path)
        elapsed_status = time.perf_counter() - start

        print(f"\nis_git_repo check: {elapsed_check * 1000:.2f}ms")
        print(f"get_git_file_status: {elapsed_status * 1000:.2f}ms")

        assert is_repo
        assert elapsed_check < 0.1, f"Git repo check took {elapsed_check:.3f}s"
        assert elapsed_status < 0.5, f"Git status took {elapsed_status:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
