import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class BacktestConfig:
    tickers: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "GOOGL"])
    start_date: str = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d")
    end_date: str = datetime.now().strftime("%Y-%m-%d")
    interval: str = "1d"
    initial_capital: float = 100_000.0
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    slippage_pct: float = 0.001
    output_dir: str = "output"
    strategy: dict[str, Any] = field(default_factory=lambda: {
        "name": "SMACrossover",
        "params": {"short_window": 50, "long_window": 200}
    })

    @classmethod
    def from_json(cls, filepath: str) -> "BacktestConfig":
        if not os.path.exists(filepath):
            print(f"[WARN] Config file {filepath} not found. Using defaults.")
            return cls()
        
        with open(filepath, "r") as f:
            data = json.load(f)
            
        # Filter out keys that aren't in the dataclass
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        
        return cls(**filtered_data)


@dataclass
class IBKRConfig:
    host: str = "https://api.ibkr.com"
    account_id: str = ""
    username: str = ""
    password: str = ""
    paper_trading: bool = True
