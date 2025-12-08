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

from ecudo import __version__
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
    help="Suppress progress messages (only errors and summary)",
)
@click.pass_context
def cli(ctx: click.Context, config_file: Path | None, quiet: bool):
    """eCUDO Crawler - Discover and process public scientific datasets."""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["quiet"] = quiet


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

    config = load_config(
        config_file=ctx.obj.get("config_file"),
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    crawler = EcudoCrawler(
        organization=organization,
        config=config,
        max_records=max_records,
        quiet=ctx.obj.get("quiet", False),
    )

    asyncio.run(crawler.run())


@cli.command("list-orgs")
@click.pass_context
def list_orgs(ctx: click.Context):
    """List all available organizations in eCUDO."""
    config = load_config(config_file=ctx.obj.get("config_file"))
    asyncio.run(_list_organizations(config))


async def _list_organizations(config: Config):
    """Async implementation of list-orgs command."""
    async with EcudoClient(base_url=config.crawler.base_url) as client:
        print("📡 Fetching list of organizations...")
        organizations = await client.get_organizations()

        if not organizations:
            print("❌ Failed to fetch organizations.")
            sys.exit(1)

        print(f"\n✅ Found {len(organizations)} organizations:\n")
        print(f"{'ID':<10} {'Name':<60} {'Link'}")
        print("-" * 100)

        for org in organizations:
            org_id = org.get("id", "?")
            name = org.get("name", "Unknown")[:58]
            link = (
                org.get("link", [""])[0]
                if isinstance(org.get("link"), list)
                else org.get("link", "")
            )
            print(f"{org_id:<10} {name:<60} {link}")


@cli.command("convert")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Output JSON file (default: input with .json extension)",
)
def convert(input_file: Path, output_file: Path | None):
    """
    Convert JSONL file to JSON array.

    INPUT_FILE is the path to the JSONL file to convert.
    """
    if output_file is None:
        output_file = input_file.with_suffix(".json")

    print(f"📄 Converting {input_file} -> {output_file}")

    datasets = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                datasets.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"⚠️ Skipping invalid JSON on line {line_num}: {e}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(datasets, f, ensure_ascii=False, indent=2)

    print(f"✅ Converted {len(datasets)} records")
    print(f"   Output: {output_file}")


@cli.command("show-config")
@click.pass_context
def show_config(ctx: click.Context):
    """Show current configuration."""
    config = load_config(config_file=ctx.obj.get("config_file"))
    config_dict = config_to_dict(config)

    print("Current configuration:\n")
    print(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))


def main():
    """Main entry point."""
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
