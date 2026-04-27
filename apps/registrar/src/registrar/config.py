"""
Registrar Configuration

Hierarchical configuration management: env vars < config file < CLI args.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_MASKED_TOKEN_MAX_LENGTH = 12


@dataclass
class OnedataConfig:
    """Onedata connection settings."""

    onezone_domain: str = "demo.onedata.org"
    oneprovider_domain: str = "provider.demo.onedata.org"
    panel_port: int = 443
    verify_ssl: bool = False


@dataclass
class TokensConfig:
    """Authentication tokens."""

    admin_token: str = ""  # Onepanel admin token
    space_owner_token: str = ""  # Onezone/Oneprovider user token
    handle_service_id: str = ""  # Optional, for DOI registration


@dataclass
class StorageConfig:
    """Storage defaults."""

    default_size: int = 1099511627776  # 1TB in bytes


@dataclass
class OutputConfig:
    """Output configuration."""

    dir: str = "./data"
    log_file: str = "registration.log"


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "info"  # debug, info, warning, error, silent


@dataclass
class Config:
    """Main configuration."""

    onedata: OnedataConfig = field(default_factory=OnedataConfig)
    tokens: TokensConfig = field(default_factory=TokensConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(
    config_file: Path | None = None,
    cli_overrides: dict | None = None,
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
        "onedata": {
            "onezone_domain": config.onedata.onezone_domain,
            "oneprovider_domain": config.onedata.oneprovider_domain,
            "panel_port": config.onedata.panel_port,
            "verify_ssl": config.onedata.verify_ssl,
        },
        "tokens": {
            "admin_token": _mask_token(config.tokens.admin_token),
            "space_owner_token": _mask_token(config.tokens.space_owner_token),
            "handle_service_id": config.tokens.handle_service_id or "(not set)",
        },
        "storage": {
            "default_size": config.storage.default_size,
        },
        "output": {
            "dir": config.output.dir,
            "log_file": config.output.log_file,
        },
        "logging": {
            "level": config.logging.level,
        },
    }


def _mask_token(token: str) -> str:
    """Mask token for display, showing only first/last 4 chars."""
    if not token:
        return "(not set)"
    if len(token) <= _MASKED_TOKEN_MAX_LENGTH:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def _load_from_env() -> dict:
    """Load configuration from environment variables."""
    config: dict[str, dict[str, Any]] = {}

    if onedata_env := _load_onedata_env():
        config["onedata"] = onedata_env
    if tokens_env := _load_tokens_env():
        config["tokens"] = tokens_env
    if storage_env := _load_storage_env():
        config["storage"] = storage_env
    if output_env := _load_output_env():
        config["output"] = output_env
    if logging_env := _load_logging_env():
        config["logging"] = logging_env

    return config


def _load_onedata_env() -> dict[str, Any]:
    """Load onedata settings from environment variables."""
    onedata: dict[str, Any] = {}
    if onezone_domain := _get_env("ONEZONE_DOMAIN"):
        onedata["onezone_domain"] = onezone_domain
    if oneprovider_domain := _get_env("ONEPROVIDER_DOMAIN"):
        onedata["oneprovider_domain"] = oneprovider_domain
    if panel_port := _get_env("PANEL_PORT"):
        onedata["panel_port"] = int(panel_port)
    if verify_ssl := _get_env("VERIFY_SSL"):
        onedata["verify_ssl"] = verify_ssl.lower() in ("true", "1", "yes")
    return onedata


def _load_tokens_env() -> dict[str, Any]:
    """Load tokens from environment variables."""
    tokens: dict[str, Any] = {}
    if admin_token := _get_env("ADMIN_TOKEN"):
        tokens["admin_token"] = admin_token
    if space_owner_token := _get_env("SPACE_OWNER_TOKEN"):
        tokens["space_owner_token"] = space_owner_token
    if handle_service_id := _get_env("HANDLE_SERVICE_ID"):
        tokens["handle_service_id"] = handle_service_id
    return tokens


def _load_storage_env() -> dict[str, Any]:
    """Load storage settings from environment variables."""
    storage: dict[str, Any] = {}
    if default_size := _get_env("DEFAULT_STORAGE_SIZE"):
        storage["default_size"] = int(default_size)
    return storage


def _load_output_env() -> dict[str, Any]:
    """Load output settings from environment variables."""
    output: dict[str, Any] = {}
    if output_dir := _get_env("OUTPUT_DIR"):
        output["dir"] = output_dir
    if log_file := _get_env("LOG_FILE"):
        output["log_file"] = log_file
    return output


def _load_logging_env() -> dict[str, Any]:
    """Load logging settings from environment variables."""
    logging: dict[str, Any] = {}
    if log_level := _get_env("LOG_LEVEL"):
        logging["level"] = log_level.lower()
    return logging


def _get_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable with REGISTRAR_ prefix."""
    return os.environ.get(f"REGISTRAR_{key}", default)


def _load_from_file(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    if not config_path.exists():
        return {}

    with open(config_path, encoding="utf-8") as f:
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
    onedata_data = data.get("onedata", {})
    tokens_data = data.get("tokens", {})
    storage_data = data.get("storage", {})
    output_data = data.get("output", {})
    logging_data = data.get("logging", {})

    onedata = OnedataConfig(**onedata_data) if onedata_data else OnedataConfig()
    tokens = TokensConfig(**tokens_data) if tokens_data else TokensConfig()
    storage = StorageConfig(**storage_data) if storage_data else StorageConfig()
    output = OutputConfig(**output_data) if output_data else OutputConfig()
    logging = LoggingConfig(**logging_data) if logging_data else LoggingConfig()

    return Config(
        onedata=onedata,
        tokens=tokens,
        storage=storage,
        output=output,
        logging=logging,
    )
