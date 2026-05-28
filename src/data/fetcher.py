import os
from datetime import datetime

import pandas as pd
import yfinance as yf


def fetch_ohlcv(
    tickers: list[str],
    start: str,
    end: str,
    interval: str = "1d",
    cache_dir: str = ".cache",
) -> dict[str, pd.DataFrame]:
    if not isinstance(tickers, list) or len(tickers) == 0:
        raise ValueError("tickers must be a non-empty list")

    os.makedirs(cache_dir, exist_ok=True)

    def _file(ticker: str) -> str:
        return os.path.join(cache_dir, f"{ticker}_{start}_{end}_{interval}.parquet")

    result = {}
    for ticker in tickers:
        path = _file(ticker)
        if os.path.exists(path):
            result[ticker] = pd.read_parquet(path)
            continue

        df = _download(ticker, start, end, interval)
        if df is not None and not df.empty:
            df.to_parquet(path)
            result[ticker] = df

    return result


def _download(
    ticker: str, start: str, end: str, interval: str
) -> pd.DataFrame | None:
    try:
        data = yf.download(
            ticker, start=start, end=end, interval=interval,
            progress=False, auto_adjust=False,
        )
    except Exception as e:
        print(f"[WARN] Failed to download {ticker}: {e}")
        return None

    if data.empty:
        print(f"[WARN] No data for {ticker}")
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data = data.xs(ticker, axis=1, level=1)

    data.columns = [c.lower() for c in data.columns]
    close_col = "adj close" if "adj close" in data.columns else "close"
    data.rename(columns={close_col: "adj_close"}, inplace=True)

    data.index = pd.to_datetime(data.index)
    data.index.name = "date"

    for col in ("adj_close", "close"):
        if col in data.columns:
            data["returns"] = data[col].pct_change()
            break

    return data


def align_data(
    data: dict[str, pd.DataFrame]
) -> tuple[pd.DatetimeIndex, pd.DataFrame]:
    if not data:
        return pd.DatetimeIndex([]), pd.DataFrame()

    prices = {}
    aligned_dates = None

    for ticker, df in data.items():
        col = "adj_close" if "adj_close" in df.columns else "close"
        series = df[col].dropna()
        prices[ticker] = series
        if aligned_dates is None:
            aligned_dates = set(series.index)
        else:
            aligned_dates &= set(series.index)

    if not aligned_dates:
        return pd.DatetimeIndex([]), pd.DataFrame()

    dates = sorted(aligned_dates)
    result = pd.DataFrame(index=dates)

    for ticker, series in prices.items():
        result[ticker] = series.loc[dates]

    return pd.DatetimeIndex(dates), result