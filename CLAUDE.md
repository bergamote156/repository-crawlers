# Project Overview

UV workspace (Python 3.12+) for discovering and registering public scientific
datasets in Onedata. Four packages:

| Package | Path | CLI | Purpose |
|---------|------|-----|---------|
| `repository-crawlers` | `apps/crawlers/` | `crawlers` | Crawl external APIs, produce `OnedataDataset` JSONL |
| `repository-registrar` | `apps/registrar/` | `registrar` | Register crawled datasets in a Onedata zone |
| `confline` | `packages/confline/` | — | Declarative config + subcommand framework (shared) |
| `onedata-dataset` | `packages/onedata-dataset/` | — | Dataset contract — JSONL records exchanged between crawlers and registrar |

## Build & run

```bash
uv sync --group dev          # install all deps (creates .venv)
make format                  # ruff fix + format
make lint                    # format-check + static-analysis + type-check (mypy)
make test                    # pytest across all packages

crawlers <plugin> crawl ...  # run a crawler plugin
registrar ...                # register datasets
```

`make lint` = `make format-check` + `make static-analysis` + `make type-check`.
Always run `make format` before committing — the CI gate checks formatting.

## Crawlers plugin system

Each plugin lives in `apps/crawlers/src/crawlers/plugins/<name>/` and extends
`CrawlerPlugin[RawT, ConfigT]`. The framework handles CLI dispatch,
parallelism, JSONL persistence, progress display, and URL validation.

When writing a new plugin, study the most similar production plugin — see
`apps/crawlers/docs/guides/writing-plugins.md` for the full guide.

# Code Style

## File header

Every non-empty Python file starts with a module docstring followed immediately
by the author block:

```python
"""
One-line (or short multi-line) description of what this module is.
"""

__author__ = "Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"
```

Empty `__init__.py` files (pure namespace markers) need no header.

## Module docstrings

State the module's purpose in 1–5 lines. Do **not** repeat information already
in class docstrings (e.g. don't list the subclass contract in the module doc
when `CrawlerPlugin.__doc__` already covers it). If the module has one
dominant class, one sentence is enough.

## Class docstrings

State **what the class is** and any non-obvious gotchas (e.g. reentrancy,
ownership of resources). Do **not** list methods or commands — those are
visible from the code and from `--help`.

```python
class EcudoPlugin(CrawlerPlugin[str, EcudoCrawlConfig]):
    """Crawler for eCUDO.pl science-data repositories."""
```

## Method / function docstrings

Proportional to complexity. One-liners are fine for obvious methods. Use
`Args:` / `Returns:` only when the contract isn't clear from the signature.
Focus on **what** is returned and edge cases, not on restating the code.

No Sphinx RST (`.. note::`, `.. warning::`, `:param foo:`, `::` code blocks).
Plain text only.

## Inline comments

Only for **why**, not **what**. The code already says what. Comment when:
- the logic is non-obvious or counter-intuitive
- a quirk of an external API or library is being worked around
- a constraint is being enforced that isn't obvious from context

Keep comments short and lowercase (unless it's a proper noun or acronym).

## Section dividers

Two tiers, used consistently across core and plugins:

**Major sections** (between top-level definitions or large class sections):

```python
# ─────────────────────────────────────────────────────────────────────────────
# Section label
# ─────────────────────────────────────────────────────────────────────────────
```

**Sub-sections** (within a class body, to group related methods):

```python
# --- Sub-section label ---
```

No ASCII-only (`---...---`) alternatives. Use UTF-8 `─` (U+2500) for major
dividers. Don't add dividers where the code structure is already obvious.

## What not to do

- Don't add a `Commands:` / `Methods:` list to class docstrings.
- Don't use Sphinx directives (`.. note::`, `:param:`, `::`) — plain text only.
- Don't write comments that restate the code (`# increment i`).
- Don't add boilerplate to intentionally empty `__init__.py` files.
- Don't use ASCII hyphen dividers (`# ------`) — use the UTF-8 style above.
