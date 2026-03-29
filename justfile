# justfile for vii - Terminal file browser

# Default recipe (list all available recipes)
default:
    @just --list

# Run all tests
test:
    python -m pytest tests/ -v

# Run tests with coverage
test-cov:
    python -m pytest tests/ -v --cov=src/vii --cov-report=term-missing

# Run tests in watch mode (requires pytest-watch)
test-watch:
    ptw tests/ -- -v

# Run a specific test file
test-file FILE:
    python -m pytest {{FILE}} -v

# Run a specific test by name pattern
test-match PATTERN:
    python -m pytest tests/ -v -k {{PATTERN}}

# Run type checking with mypy
typecheck:
    python -m mypy src/vii/ --show-error-codes

# Run type checking on specific files
typecheck-file FILES:
    python -m mypy {{FILES}} --show-error-codes

# Run linter (ruff)
lint:
    ruff check src/ tests/

# Auto-fix linting issues
lint-fix:
    ruff check --fix src/ tests/

# Format code with ruff
format:
    ruff format src/ tests/

# Check formatting without making changes
format-check:
    ruff format --check src/ tests/

# Run all quality checks (tests, typecheck, lint)
check: test typecheck lint

# Run the vii application
run PATH=".":
    python -m vii {{PATH}}

# Install development dependencies
install:
    pip install -e ".[dev]"

# Install in editable mode (basic)
install-dev:
    pip install -e .

# Clean up cache and build artifacts
clean:
    rm -rf .pytest_cache/
    rm -rf .mypy_cache/
    rm -rf .ruff_cache/
    rm -rf __pycache__/
    rm -rf src/**/__pycache__/
    rm -rf tests/**/__pycache__/
    rm -rf *.egg-info/
    rm -rf dist/
    rm -rf build/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete

# Build distribution packages
build:
    python -m build

# Show project statistics
stats:
    @echo "Lines of code:"
    @find src -name "*.py" | xargs wc -l | tail -1
    @echo "\nTest files:"
    @find tests -name "*.py" | xargs wc -l | tail -1
    @echo "\nTest count:"
    @grep -r "def test_" tests/ | wc -l

# Run performance tests only
test-perf:
    python -m pytest tests/test_performance.py -v

# Run integration tests only  
test-integration:
    python -m pytest tests/test_app.py::TestVii::test_jk_scrolls_in_git_commit_view_integration -v

# Quick check before commit (fast tests + typecheck)
pre-commit: format lint typecheck test

# Full CI check (everything)
ci: clean check test-cov

# Show coverage report in HTML
cov-html:
    python -m pytest tests/ --cov=src/vii --cov-report=html
    @echo "Open htmlcov/index.html to view coverage report"
