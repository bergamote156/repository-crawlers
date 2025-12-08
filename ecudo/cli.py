"""
eCUDO CLI

Command-line interface for crawling eCUDO.pl datasets.
"""

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import click
import yaml

from ecudo import __version__
from ecudo.config import Config, config_to_dict, load_config
from ecudo.crawler import EcudoClient, RecordIDIterator
from ecudo.orchestration import ParallelFetcher, ProcessingStats
from ecudo.parsers.ecudo import parse_record
from ecudo.processors import DiversityFilter, Processor, ProcessorPipeline, URLValidator
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import MetadataFetcher
from ecudo.processors.writers import JSONLWriter, RawRecordWriter
from ecudo.serializers import OpenAIRESerializer


class EcudoCrawler:
    """Orchestrates crawling of an eCUDO organization."""

    def __init__(
        self,
        organization: str,
        config: Config,
        max_records: int | None = None,
        quiet: bool = False,
    ):
        self.organization = organization
        self.config = config
        self.max_records = max_records
        self.quiet = quiet

        self._raw_output: Path | None = None
        self._processed_output: Path | None = None

    def log(self, message: str) -> None:
        """Print message if not in quiet mode."""
        if not self.quiet:
            print(message)

    async def run(self) -> None:
        """Execute the crawl."""
        self.log("=" * 80)
        self.log(f"eCUDO Crawler - Organization: {self.organization.upper()}")
        self.log("=" * 80)

        self._prepare_output_paths()

        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                EcudoClient(
                    base_url=self.config.crawler.base_url,
                    timeout=self.config.crawler.timeout,
                    max_retries=self.config.crawler.max_retries,
                )
            )

            await self._validate_organization(client)

            processors = self._build_pipeline_processors(client)
            pipeline = ProcessorPipeline(processors)
            await pipeline.open()
            stack.push_async_callback(pipeline.close)

            id_iterator = RecordIDIterator(
                client=client,
                org_id=self.organization,
                page_size=self.config.crawler.page_size,
                max_records=self.max_records,
            )

            stats, pipeline_stats = await self._run_fetcher(id_iterator, pipeline)
            self._print_summary(stats, pipeline_stats)

    def _prepare_output_paths(self) -> None:
        """Ensure output directory exists and set output file paths."""
        output_dir = Path(self.config.output.dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._raw_output = output_dir / f"{self.organization}_raw.jsonl"
        self._processed_output = output_dir / f"{self.organization}_processed.jsonl"

    async def _validate_organization(self, client: EcudoClient) -> None:
        """Ensure the requested organization exists."""
        self.log("📡 Validating organization...")
        orgs = await client.get_organizations()
        if not any(o["id"] == self.organization for o in orgs):
            print(f"❌ Organization '{self.organization}' not found.")
            print(f"   Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)
        self.log(f"✅ Found organization: {self.organization}")

    def _build_pipeline_processors(self, client: EcudoClient) -> list[Processor]:
        """Assemble the processing pipeline based on configuration."""
        self.log("\n📦 Building processing pipeline...")
        processors: list[Processor] = []

        self.log("   ✓ MetadataFetcher: fetch and parse JSON-LD")
        processors.append(MetadataFetcher(client, parse_record))

        if self.config.processors.url_validator.enabled:
            self.log("   ✓ URLValidator: check URL accessibility")
            processors.append(URLValidator(client))
        else:
            self.log("   ⊘ URLValidator: disabled")

        if self.config.processors.diversity_filter.enabled:
            df_cfg = self.config.processors.diversity_filter
            self.log(
                f"   ✓ DiversityFilter: max {df_cfg.max_similar} similar "
                f"({df_cfg.similarity_threshold:.0%} threshold)"
            )
            processors.append(
                DiversityFilter(
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                )
            )
        else:
            self.log("   ⊘ DiversityFilter: disabled")

        self.log(f"   ✓ RawRecordWriter: {self._raw_output}")
        processors.append(RawRecordWriter(self._raw_output))

        serializer = OpenAIRESerializer()
        self.log("   ✓ OnedataConverter: build Onedata dataset with OpenAIRE XML")
        processors.append(OnedataConverter(serializer))

        self.log(f"   ✓ JSONLWriter: {self._processed_output}")
        processors.append(JSONLWriter(self._processed_output))

        return processors

    async def _run_fetcher(
        self,
        id_iterator: RecordIDIterator,
        pipeline: ProcessorPipeline,
    ) -> tuple[ProcessingStats, dict]:
        """Execute the parallel fetcher and return run statistics."""
        self.log(f"\n🚀 Starting parallel crawl of {self.organization}...")
        if self.max_records:
            self.log(f"   Limit: {self.max_records} records")
        self.log(f"   Concurrency: {self.config.crawler.concurrency} workers")
        self.log(f"   Queue size: {self.config.crawler.queue_size}")

        fetcher = ParallelFetcher(
            concurrency=self.config.crawler.concurrency,
            queue_size=self.config.crawler.queue_size,
            verbose=not self.quiet,
        )

        stats = await fetcher.run(id_source=id_iterator, pipeline=pipeline)
        pipeline_stats = pipeline.get_stats()
        return stats, pipeline_stats

    def _print_summary(self, stats: ProcessingStats, pipeline_stats: dict) -> None:
        """Print final crawl summary."""
        print("\n" + "=" * 80)
        print("Crawl Complete!")
        print("=" * 80)
        print(f"Raw datasets saved to:       {self._raw_output}")
        print(f"Processed datasets saved to: {self._processed_output}")
        print(f"\nStatistics: {stats}")

        if pipeline_stats.get("processors"):
            print("\nProcessor statistics:")
            for name, proc_stats in pipeline_stats["processors"].items():
                stats_str = ", ".join(f"{k}: {v}" for k, v in proc_stats.items())
                print(f"   {name}: {stats_str}")

        print("\nNext steps:")
        print(
            f"  1. Convert JSONL to JSON: python -m ecudo convert {self._processed_output}"
        )
        print("  2. Run dataset_registrar.py with the converted file")
        print("=" * 80)


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
