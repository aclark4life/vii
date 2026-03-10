# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a2] - 2026-03-10

### Added

- Two-panel layout: directory tree sidebar and file content preview
- File content preview panel when navigating the directory tree
- Scrollable content panel with focus-aware navigation
- Syntax highlighting for Python files
- Syntax highlighting extended to many common file types:
  - Shell scripts (bash, zsh, fish)
  - Config files (toml, yaml, json, ini)
  - Markup (markdown, html, xml, css)
  - JavaScript/TypeScript
  - C/C++
  - Rust, Go, Ruby, Java, Kotlin, Swift, PHP, SQL, Lua, Perl
  - Special files (Dockerfile, Makefile, .bashrc, etc.)
- Vim-style search (`/`) in content panel with match highlighting
- Search in sidebar panel for finding files/directories by name
- `n/N` keys to navigate between search matches
- `Enter` key in content panel to open file in editor
- `e` key to edit selected file
- `Ctrl+F/B` for page up/down navigation in sidebar
- Draggable splitter between sidebar and content panels for resizable layout
- Syntax highlighting theme syncs with Textual app theme (dark/light)

### Changed

- `Enter` now switches focus to content panel (use `e` to edit)

### Fixed

- Vim h/l keybindings now work correctly in DirectoryTree
- Test assertions updated to match actual application behavior

## [0.1.0a1] - 2026-03-09

### Added

- Initial alpha release
- Terminal-based file browser using Textual framework
- Directory tree navigation with vim-style keybindings (j/k/h/l/g/G)
- Automatic editor detection (checks VISUAL, EDITOR env vars, then common editors)
- Support for both terminal editors (vim, nvim, nano, etc.) and GUI editors (VS Code, etc.)
- Keyboard shortcuts:
  - `j/k` - Navigate up/down
  - `h/l` - Collapse/expand directories
  - `g/G` - Go to top/bottom
  - `Tab` - Switch focus between panels
  - `q` - Quit
- Pre-commit hooks for code quality with ruff (replaced black, flake8, and isort)
- Comprehensive test suite

[Unreleased]: https://github.com/aclark4life/vii/compare/v0.1.0a2...HEAD
[0.1.0a2]: https://github.com/aclark4life/vii/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/aclark4life/vii/releases/tag/v0.1.0a1
