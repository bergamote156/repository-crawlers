"""
eCUDO CLI

Command-line interface for crawling eCUDO.pl datasets.
"""

import asyncio
import json
import sys
from pathlib import Path

import click
import yaml

from ecudo import __version__, output
from ecudo.config import Config, config_to_dict, load_config
from ecudo.crawler import EcudoCrawler
from ecudo.ecudo_api import EcudoClient


@click.group()
@click.version_option(version=__version__, prog_name="ecudo")
@click.option(
    "--config",
    "-c",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file (YAML)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress progress messages (only warnings, errors and summary)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed debug output",
)
@click.pass_context
def cli(ctx: click.Context, config_file: Path | None, quiet: bool, verbose: bool):
    """eCUDO Crawler - Discover and process public scientific datasets."""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file

    # Determine log level from flags (verbose takes precedence)
    if verbose:
        ctx.obj["log_level"] = "debug"
    elif quiet:
        ctx.obj["log_level"] = "warning"
    else:
        ctx.obj["log_level"] = None  # Use config/env default


@cli.command()
@click.argument("organization")
@click.option(
    "--max-records",
    "-n",
    type=int,
    default=None,
    help="Maximum number of records to crawl (default: all)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for crawled data",
)
@click.option(
    "--max-similar",
    type=int,
    default=None,
    help="Maximum similar datasets per group (diversity filter)",
)
@click.option(
    "--similarity-threshold",
    type=float,
    default=None,
    help="Similarity threshold for diversity filter (0.0-1.0)",
)
@click.option(
    "--no-url-validation",
    is_flag=True,
    default=False,
    help="Disable URL validation (faster but may include broken links)",
)
@click.option(
    "--no-diversity-filter",
    is_flag=True,
    default=False,
    help="Disable diversity filter (include all datasets)",
)
@click.option(
    "--concurrency",
    type=int,
    default=None,
    help="Number of concurrent workers",
)
@click.option(
    "--queue-size",
    type=int,
    default=None,
    help="Queue size for backpressure control",
)
@click.pass_context
def crawl(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ctx: click.Context,
    organization: str,
    max_records: int | None,
    output_dir: Path | None,
    max_similar: int | None,
    similarity_threshold: float | None,
    no_url_validation: bool,
    no_diversity_filter: bool,
    concurrency: int | None,
    queue_size: int | None,
):
    """
    Crawl datasets from an eCUDO organization.

    ORGANIZATION is the organization ID (e.g., iopan, mir, pgi, ug, usz, apsl, im).
    """
    # Build CLI overrides
    cli_overrides: dict = {}

    if output_dir:
        cli_overrides.setdefault("output", {})["dir"] = str(output_dir)
    if max_similar is not None:
        cli_overrides.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "max_similar"
        ] = max_similar
    if similarity_threshold is not None:
        cli_overrides.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "similarity_threshold"
        ] = similarity_threshold
    if no_url_validation:
        cli_overrides.setdefault("processors", {}).setdefault("url_validator", {})[
            "enabled"
        ] = False
    if no_diversity_filter:
        cli_overrides.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "enabled"
        ] = False
    if concurrency is not None:
        cli_overrides.setdefault("crawler", {})["concurrency"] = concurrency
    if queue_size is not None:
        cli_overrides.setdefault("crawler", {})["queue_size"] = queue_size

    # Apply log level from CLI flags
    if log_level := ctx.obj.get("log_level"):
        cli_overrides.setdefault("logging", {})["level"] = log_level

    config = load_config(
        config_file=ctx.obj.get("config_file"),
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    # Initialize output module with configured level
    output.set_level(config.logging.level)

    crawler = EcudoCrawler(
        organization=organization,
        config=config,
        max_records=max_records,
    )

    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        # Graceful shutdown handled in crawler.run()
        pass


@cli.command("list-orgs")
@click.pass_context
def list_orgs(ctx: click.Context):
    """List all available organizations in eCUDO."""
    config = load_config(config_file=ctx.obj.get("config_file"))
    asyncio.run(_list_organizations(config))


async def _list_organizations(config: Config):
    """Async implementation of list-orgs command."""
    async with EcudoClient(base_url=config.crawler.base_url) as client:
        output.info("📡 Fetching list of organizations...")
        organizations = await client.get_organizations()

        if not organizations:
            output.error("❌ Failed to fetch organizations.")
            sys.exit(1)

        output.always(f"\n✅ Found {len(organizations)} organizations:\n")
        output.always(f"{'ID':<10} {'Name':<60} {'Link'}")
        output.always("-" * 100)

        for org in organizations:
            org_id = org.get("id", "?")
            name = org.get("name", "Unknown")[:58]
            link = (
                org.get("link", [""])[0]
                if isinstance(org.get("link"), list)
                else org.get("link", "")
            )
            output.always(f"{org_id:<10} {name:<60} {link}")


@cli.command("convert")
@click.argument("input_file_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    "output_file_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output JSON file (default: input with .json extension)",
)
def convert(input_file_path: Path, output_file_path: Path | None):
    """
    Convert JSONL file to JSON array.

    INPUT_FILE is the path to the JSONL file to convert.
    """
    out_file = (
        output_file_path if output_file_path else input_file_path.with_suffix(".json")
    )

    output.info(f"📄 Converting {input_file_path} -> {out_file}")

    datasets = []
    with open(input_file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                datasets.append(json.loads(line))
            except json.JSONDecodeError as e:
                output.warning(f"⚠️ Skipping invalid JSON on line {line_num}: {e}")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(datasets, f, ensure_ascii=False, indent=2)

    output.always(f"✅ Converted {len(datasets)} records")
    output.always(f"   Output: {out_file}")


@cli.command("show-config")
@click.pass_context
def show_config(ctx: click.Context):
    """Show current configuration."""
    config = load_config(config_file=ctx.obj.get("config_file"))
    config_dict = config_to_dict(config)

    output.always("Current configuration:\n")
    output.always(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))


def main():
    """Main entry point."""
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
