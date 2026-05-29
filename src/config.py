"""Load backtest settings from config.json (project root)."""

import json
import os
from dataclasses import dataclass
from typing import Any

CONFIG_FILENAME = "config.json"
EXAMPLE_CONFIG_FILENAME = "config.example.json"
VALID_DATA_PROVIDERS = ("yfinance", "alphavantage", "stockdata", "alpaca", "local")


def project_root() -> str:
    """Repository root (parent of src/)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def default_config_path() -> str:
    return os.path.join(project_root(), CONFIG_FILENAME)


@dataclass
class BacktestConfig:
    """Backtest settings; all values come from config.json."""

    tickers: list[str]
    start_date: str
    end_date: str
    interval: str
    data_provider: str
    initial_capital: float
    commission_per_share: float
    commission_min: float
    slippage_pct: float
    output_dir: str
    strategy: dict[str, Any]
    data_dir: str = "data"

    @classmethod
    def load(cls, filepath: str | None = None) -> "BacktestConfig":
        """Load settings from config.json (or the given path)."""
        path = filepath or default_config_path()
        if not os.path.exists(path):
            example = os.path.join(os.path.dirname(path), EXAMPLE_CONFIG_FILENAME)
            raise FileNotFoundError(
                f"Config not found: {path}\n"
                f"Copy {EXAMPLE_CONFIG_FILENAME} to {CONFIG_FILENAME} and edit your settings."
            )

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        optional_keys = {"data_dir"}
        required_keys = valid_keys - optional_keys
        missing = required_keys - data.keys()
        if missing:
            raise ValueError(
                f"config.json is missing required keys: {sorted(missing)}"
            )

        unknown = set(data.keys()) - valid_keys
        if unknown:
            print(f"[WARN] Ignoring unknown config keys: {sorted(unknown)}")

        filtered = {k: data[k] for k in valid_keys if k in data}
        if "data_dir" not in filtered:
            filtered["data_dir"] = "data"
        cfg = cls(**filtered)

        if cfg.data_provider not in VALID_DATA_PROVIDERS:
            raise ValueError(
                f"Invalid data_provider '{cfg.data_provider}'. "
                f"Use one of: {', '.join(VALID_DATA_PROVIDERS)}"
            )

        return cfg

    # Kept for callers that already use from_json
    @classmethod
    def from_json(cls, filepath: str) -> "BacktestConfig":
        return cls.load(filepath)


@dataclass
class IBKRConfig:
    host: str = "https://api.ibkr.com"
    account_id: str = ""
    username: str = ""
    password: str = ""
    paper_trading: bool = True
