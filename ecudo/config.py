"""
eCUDO Configuration

Hierarchical configuration management: env vars < config file < CLI args.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class CrawlerConfig:
    """Crawler configuration."""

    base_url: str = "http://central.ecudo.pl"
    page_size: int = 200
    concurrency: int = 128
    queue_size: int = 1000
    timeout: int = 15
    max_retries: int = 3


@dataclass
class DiversityFilterConfig:
    """Diversity filter configuration."""

    enabled: bool = True
    max_similar: int = 10
    similarity_threshold: float = 0.85


@dataclass
class URLValidatorConfig:
    """URL validator configuration."""

    enabled: bool = True


@dataclass
class ProcessorsConfig:
    """Processors configuration."""

    diversity_filter: DiversityFilterConfig = field(
        default_factory=DiversityFilterConfig
    )
    url_validator: URLValidatorConfig = field(default_factory=URLValidatorConfig)


@dataclass
class OutputConfig:
    """Output configuration."""

    dir: str = "./data"


@dataclass
class Config:
    """Main configuration."""

    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    processors: ProcessorsConfig = field(default_factory=ProcessorsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with ECUDO_ prefix."""
    return os.environ.get(f"ECUDO_{key}", default)


def _load_from_env() -> dict:
    """Load configuration from environment variables."""
    config: dict[str, dict[str, Any]] = {}

    # Crawler settings
    if base_url := _get_env("BASE_URL"):
        config.setdefault("crawler", {})["base_url"] = base_url
    if page_size := _get_env("PAGE_SIZE"):
        config.setdefault("crawler", {})["page_size"] = int(page_size)
    if concurrency := _get_env("CONCURRENCY"):
        config.setdefault("crawler", {})["concurrency"] = int(concurrency)
    if queue_size := _get_env("QUEUE_SIZE"):
        config.setdefault("crawler", {})["queue_size"] = int(queue_size)
    if timeout := _get_env("TIMEOUT"):
        config.setdefault("crawler", {})["timeout"] = int(timeout)
    if max_retries := _get_env("MAX_RETRIES"):
        config.setdefault("crawler", {})["max_retries"] = int(max_retries)

    # Processors settings
    if diversity_enabled := _get_env("DIVERSITY_FILTER_ENABLED"):
        config.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "enabled"
        ] = diversity_enabled.lower() in ("true", "1", "yes")
    if max_similar := _get_env("DIVERSITY_MAX_SIMILAR"):
        config.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "max_similar"
        ] = int(max_similar)
    if similarity_threshold := _get_env("DIVERSITY_SIMILARITY_THRESHOLD"):
        config.setdefault("processors", {}).setdefault("diversity_filter", {})[
            "similarity_threshold"
        ] = float(similarity_threshold)
    if url_validator_enabled := _get_env("URL_VALIDATOR_ENABLED"):
        config.setdefault("processors", {}).setdefault("url_validator", {})[
            "enabled"
        ] = url_validator_enabled.lower() in ("true", "1", "yes")

    # Output settings
    if output_dir := _get_env("OUTPUT_DIR"):
        config.setdefault("output", {})["dir"] = output_dir

    return config


def _load_from_file(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_config(data: dict) -> Config:
    """Convert dictionary to Config dataclass."""
    crawler_data = data.get("crawler", {})
    processors_data = data.get("processors", {})
    output_data = data.get("output", {})

    crawler = CrawlerConfig(**crawler_data) if crawler_data else CrawlerConfig()

    diversity_filter_data = processors_data.get("diversity_filter", {})
    url_validator_data = processors_data.get("url_validator", {})

    processors = ProcessorsConfig(
        diversity_filter=(
            DiversityFilterConfig(**diversity_filter_data)
            if diversity_filter_data
            else DiversityFilterConfig()
        ),
        url_validator=(
            URLValidatorConfig(**url_validator_data)
            if url_validator_data
            else URLValidatorConfig()
        ),
    )

    output = OutputConfig(**output_data) if output_data else OutputConfig()

    return Config(crawler=crawler, processors=processors, output=output)


def load_config(
    config_file: Optional[Path] = None,
    cli_overrides: Optional[dict] = None,
) -> Config:
    """
    Load configuration with hierarchy: env vars < config file < CLI args.

    Args:
        config_file: Path to YAML config file (optional)
        cli_overrides: Dictionary of CLI overrides (optional)

    Returns:
        Merged Config object
    """
    # Layer 1: Environment variables
    merged = _load_from_env()

    # Layer 2: Config file
    if config_file:
        file_config = _load_from_file(config_file)
        merged = _deep_merge(merged, file_config)

    # Layer 3: CLI overrides
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    return _dict_to_config(merged)


def config_to_dict(config: Config) -> dict:
    """Convert Config dataclass to dictionary."""
    return {
        "crawler": {
            "base_url": config.crawler.base_url,
            "page_size": config.crawler.page_size,
            "concurrency": config.crawler.concurrency,
            "queue_size": config.crawler.queue_size,
            "timeout": config.crawler.timeout,
            "max_retries": config.crawler.max_retries,
        },
        "processors": {
            "diversity_filter": {
                "enabled": config.processors.diversity_filter.enabled,
                "max_similar": config.processors.diversity_filter.max_similar,
                "similarity_threshold": config.processors.diversity_filter.similarity_threshold,
            },
            "url_validator": {
                "enabled": config.processors.url_validator.enabled,
            },
        },
        "output": {
            "dir": config.output.dir,
        },
    }
