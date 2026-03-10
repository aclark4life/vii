# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a2] - Unreleased

### Added

- Draggable splitter between sidebar and content panels for resizable layout
- Syntax highlighting for many common file types:
  - Shell scripts (bash, zsh, fish)
  - Config files (toml, yaml, json, ini)
  - Markup (markdown, html, xml, css)
  - JavaScript/TypeScript
  - C/C++
  - Rust, Go, Ruby, Java, Kotlin, Swift, PHP, SQL, Lua, Perl
  - Special files (Dockerfile, Makefile, .bashrc, etc.)

### Fixed

- Test assertions updated to match actual application behavior

## [0.1.0a1] - 2026-03-09

### Added

- Initial alpha release
- Terminal-based file browser using Textual framework
- Directory tree navigation with vim-style keybindings (j/k/h/l/g/G)
- File content preview panel with syntax highlighting for Python
- Automatic editor detection (checks VISUAL, EDITOR env vars, then common editors)
- Support for both terminal editors (vim, nvim, nano, etc.) and GUI editors (VS Code, etc.)
- Two-panel layout: directory tree sidebar and content preview
- Keyboard shortcuts:
  - `j/k` - Navigate up/down
  - `h/l` - Collapse/expand directories
  - `g/G` - Go to top/bottom
  - `e` - Edit selected file
  - `Enter` - Switch focus to content panel
  - `Tab` - Switch focus between panels
  - `/` - Search in current panel
  - `n/N` - Next/previous search match
  - `q` - Quit
- Search functionality in both sidebar (file names) and content panel (file contents)
- Scrollable content panel with Page Up/Down support
- Pre-commit hooks with ruff for linting and formatting
- Comprehensive test suite

[Unreleased]: https://github.com/aclark4life/vii/compare/v0.1.0a2...HEAD
[0.1.0a2]: https://github.com/aclark4life/vii/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/aclark4life/vii/releases/tag/v0.1.0a1
