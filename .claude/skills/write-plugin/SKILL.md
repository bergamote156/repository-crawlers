---
name: write-plugin
description: >
  Create a new crawler plugin from scratch — config, API client, parser, plugin
  class, registration, and verification. Use whenever the user wants to add a
  new data-source crawler, says "write a plugin", "add a crawler for X",
  "create a new plugin", or discusses integrating a new API into the crawler
  framework. Also use when the user points at an API and asks how to crawl it,
  wants to scaffold a plugin skeleton, or says "I want to index data from this
  REST API" or "add a new data source to the pipeline."
---

# Write Plugin

You are creating a new crawler plugin for the Onedata repository-crawlers
framework. A plugin crawls an external API and produces `OnedataDataset`
records with metadata XML and file listings.

## Before you write any code

1. Read `apps/crawlers/docs/guides/writing-plugins.md` — the authoritative
   framework guide (config system, lifecycle, commands, registration).
2. Read the production plugin chosen in "Pick a reference plugin" below —
   `plugin.py`, `api.py`, and `parser.py`. These are always up to date and are
   your primary source of truth for code patterns.

Add the mandatory file header (`__author__` etc.) to every non-empty `.py`
file you create — the project's CLAUDE.md defines the exact format.

## Gather requirements

Ask the user these questions (skip any they've already answered):

1. **Data source** — what API are we crawling? Name, base URL, docs link if
   available.
2. **What to crawl** — what does one "dataset" look like? What fields matter?
3. **Pagination** — how does the API paginate? (offset, cursor/next-link,
   full listing, seed file, HTML scraping)
4. **Detail fetch** — does `iterate_datasets` yield full items, or just IDs
   that need a second fetch in `process()`?
5. **Files** — how do we discover download URLs? (direct from API response,
   recursive folder walk, constructed from pattern, scraped from HTML)
6. **Metadata format** — DataCite (default, used by 4/5 plugins) or OpenAIRE?
   What metadata fields does the API provide?
7. **Extra commands** — should we add a `list-collections` / `list-orgs`
   style command?
8. **Plugin name** — short kebab-case name for the CLI (`crawlers <name> crawl ...`).
9. **Author** — name for the `__author__` field in file headers (this is your
   plugin, sign it with your name).

## Pick a reference plugin

Based on the answers, choose the most similar existing plugin for the agent
to study as a reference:

| If the pattern is... | Study this plugin |
|----------------------|-------------------|
| ID-based iteration, detail fetch in `process()` | `ecudo` |
| Full items from API listing, direct parse | `eodc` |
| HTML scraping, RDF/JSON-LD | `bgee` |
| Recursive folder/file resolution in `process()` | `vip` |
| Seed file, branched typed fetch | `topanat` |

Read the chosen plugin's `plugin.py`, `api.py`, and `parser.py` before
writing code.

## Generate the plugin

Create the directory `apps/crawlers/src/crawlers/plugins/<name>/` with:

### `__init__.py` — empty file

A single-line empty file (just a newline). No header, no docstring.

### `plugin.py` — plugin class + config

Contains:
- Config classes (`<Name>ApiConfig`, `<Name>CrawlConfig`)
- Plugin class extending `CrawlerPlugin[RawT, ConfigT]`
- Extra `@command` methods if requested

### `api.py` — API client facade

Contains:
- `<Name>Client` class taking `HttpClient` in `__init__`
- Iteration method(s) as async generators
- Single-item fetch methods returning `Result`
- Any `TypedDict` or parameter dataclasses for API responses
- Module-level helper functions for response parsing

### `parser.py` — data mapping

Contains:
- Pure mapping function(s) or stateless parser class — no I/O
- Module-level constants for fixed metadata values
- Returns `Ok(OnedataDataset)`, `Err(failure)`, or `None`

### `models.py` — only if needed

Create only when config classes or domain types are too large for `plugin.py`.

## Register the plugin

Add the import and instance to
`apps/crawlers/src/crawlers/plugins/__init__.py`:

```python
from crawlers.plugins.<name>.plugin import <Name>Plugin

REGISTERED_PLUGINS: list[CrawlerPlugin[Any, Any]] = [
    ...,
    <Name>Plugin(),
]
```

## Format and lint

After generating all files, run:

```bash
make format   # ruff fix + format (fixes imports, style)
make lint     # format-check + static-analysis + type-check (mypy)
```

Fix any errors reported by `make lint` before proceeding. The formatter
handles import ordering and code style — don't waste time hand-tuning those.

## Verify

Suggest these commands to the user:

```bash
crawlers <name> crawl --help        # confirm args appear
crawlers <name> crawl <arg> -n 5    # small test run
```

And tell them what to check in the output directory.

## Quality checklist

Before declaring the plugin complete, verify:

- [ ] `make format` and `make lint` pass clean
- [ ] Config uses diamond inheritance (`ApiConfig(HttpConfig)` + `CrawlConfig(ApiConfig, CrawlConfig, kw_only=True)`)
- [ ] Pagination logic lives in `api.py`, not in the plugin
- [ ] Parser has no I/O — pure mapping only
- [ ] `target_dir` uses `title.replace("/", "-")`
- [ ] Files are `tuple(...)`, not `list`
- [ ] `console.*` for output, never `logging` or `print`
- [ ] Plugin is registered in `__init__.py`
