# Contributing

Thank you for your interest in contributing to Repository Crawlers!

## Setup

You need [uv](https://docs.astral.sh/uv/) (the Python package manager from
Astral). Then:

```bash
git clone https://github.com/onedata/repository-crawlers.git
cd repository-crawlers
make sync
```

This installs all workspace packages, development tools, and plugin
dependencies into a local `.venv`.

## Making changes

1. Fork the repo and create a branch from `develop`.
2. Make your changes.
3. Run `make format` to auto-format with ruff.
4. Run `make lint` — must pass (format check + static analysis + type check).
5. Run `make test` — must pass.
6. Open a Pull Request against `develop`.

CI runs both `make lint` and `make test` on every PR automatically. Both
checks must be green before a PR can be merged.

## Writing a new crawler plugin

The project has a plugin architecture — each data source gets its own
plugin under `apps/crawlers/src/crawlers/plugins/<name>/`.

See the [Writing Plugins](apps/crawlers/docs/guides/writing-plugins.md) guide
for step-by-step instructions covering configuration, lifecycle hooks,
iteration, processing, and registration.

### Using AI assistance

This repository includes a [`CLAUDE.md`](CLAUDE.md) file with project
conventions (code style, file headers, section dividers, docstring rules) that
AI coding assistants can follow. If you use [Cursor](https://cursor.com/) or
[Claude Code](https://docs.anthropic.com/en/docs/claude-code), the conventions
are picked up automatically.

There is also a dedicated
[write-plugin skill](.claude/skills/write-plugin/SKILL.md) that walks an AI
agent through the full plugin creation process — from gathering requirements
to generating code, registering the plugin, and verifying it works.

## Code style

- **Python 3.12+**
- Formatted and linted with **ruff** (`make format` / `make lint`)
- Type-checked with **mypy** (`make lint` includes this)
- Every non-empty Python file starts with a module docstring followed by the
  `__author__` / `__copyright__` / `__license__` block — see any existing
  module for the exact pattern, or refer to [`CLAUDE.md`](CLAUDE.md)
- Comments explain *why*, not *what*

## Reporting issues

Open an issue on GitHub. Include:
- What you were trying to do
- What happened instead
- Steps to reproduce (if applicable)
- Python version and OS

## License

By contributing you agree that your contributions will be licensed under the
[MIT License](LICENSE.txt).
