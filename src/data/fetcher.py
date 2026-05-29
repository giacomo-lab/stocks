import os

import pandas as pd
import yfinance as yf

from src.data import alphavantage, local_files, stockdata
from src.data import alpaca as alpaca_data

VALID_PROVIDERS = ("yfinance", "alphavantage", "stockdata", "alpaca", "local")


def fetch_ohlcv(
    tickers: list[str],
    start: str,
    end: str,
    interval: str = "1d",
    cache_dir: str = ".cache",
    provider: str = "yfinance",
    data_dir: str | None = None,
) -> dict[str, pd.DataFrame]:
    if not isinstance(tickers, list) or len(tickers) == 0:
        raise ValueError("tickers must be a non-empty list")
    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. Choose from: {', '.join(VALID_PROVIDERS)}"
        )
    if provider == "alphavantage" and interval != "1d":
        raise ValueError(
            "Alpha Vantage free tier supports daily (1d) only. "
            "Use data_provider: yfinance for intraday, or upgrade Alpha Vantage."
        )

    os.makedirs(cache_dir, exist_ok=True)

    def _file(ticker: str) -> str:
        return os.path.join(cache_dir, f"{ticker}_{start}_{end}_{interval}.parquet")

    result = {}
    for ticker in tickers:
        path = _file(ticker)
        if os.path.exists(path):
            result[ticker] = pd.read_parquet(path)
            continue

        df = _download(ticker, start, end, interval, provider, data_dir)
        if df is not None and not df.empty:
            df.to_parquet(path)
            result[ticker] = df

    return result


def _download(
    ticker: str,
    start: str,
    end: str,
    interval: str,
    provider: str,
    data_dir: str | None = None,
) -> pd.DataFrame | None:
    if provider == "alphavantage":
        return _download_alphavantage(ticker, start, end)
    if provider == "stockdata":
        return _download_stockdata(ticker, start, end, interval)
    if provider == "alpaca":
        return _download_alpaca(ticker, start, end, interval)
    if provider == "local":
        return _download_local(ticker, start, end, interval, data_dir)
    return _download_yfinance(ticker, start, end, interval)


def _download_yfinance(
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


def _download_alphavantage(
    ticker: str, start: str, end: str
) -> pd.DataFrame | None:
    try:
        data = alphavantage.fetch_daily(ticker)
    except Exception as e:
        print(f"[WARN] Failed to download {ticker} from Alpha Vantage: {e}")
        return None

    if data.empty:
        print(f"[WARN] No data for {ticker}")
        return None

    # Filter to requested date range (compact returns ~100 most recent bars)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    data = data.loc[(data.index >= start_ts) & (data.index <= end_ts)]

    if data.empty:
        print(
            f"[WARN] No data for {ticker} in range {start} to {end} "
            "(Alpha Vantage free tier returns ~100 recent daily bars)"
        )
        return None

    return data


def _download_stockdata(
    ticker: str, start: str, end: str, interval: str
) -> pd.DataFrame | None:
    try:
        data = stockdata.fetch_ohlcv_range(ticker, start, end, interval)
    except Exception as e:
        print(f"[WARN] Failed to download {ticker} from StockData.org: {e}")
        return None

    if data.empty:
        print(f"[WARN] No data for {ticker} in range {start} to {end}")
        return None

    return data


def _download_alpaca(
    ticker: str, start: str, end: str, interval: str
) -> pd.DataFrame | None:
    try:
        data = alpaca_data.fetch_bars_range(ticker, start, end, interval)
    except ValueError as e:
        # Unsupported interval — re-raise so caller gets a clear message
        raise
    except Exception as e:
        print(f"[WARN] Failed to download {ticker} from Alpaca: {e}")
        return None

    if data.empty:
        print(f"[WARN] No data for {ticker} in range {start} to {end}")
        return None

    return data


def _download_local(
    ticker: str,
    start: str,
    end: str,
    interval: str,
    data_dir: str | None,
) -> pd.DataFrame | None:
    try:
        data = local_files.load_ohlcv(ticker, start, end, interval, data_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"[WARN] {e}")
        return None
    except Exception as e:
        print(f"[WARN] Failed to load {ticker} from local files: {e}")
        return None

    if data.empty:
        return None

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
