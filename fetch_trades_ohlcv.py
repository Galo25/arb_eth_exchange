import argparse
import os
import sys
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import ccxt


def parse_datetime_utc(dt_str: str) -> datetime:
    dt = pd.to_datetime(dt_str, utc=True)
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    return dt.to_pydatetime()


def get_exchange(exchange_name: str) -> ccxt.Exchange:
    name = exchange_name.lower()
    if name == "binance":
        exchange = ccxt.binance({'enableRateLimit': True})
    elif name in ("coinbase", "coinbasepro", "coinbasepro2"):
        # CCXT unified name is coinbase for new API
        exchange = ccxt.coinbase({'enableRateLimit': True})
    elif name == "kraken":
        exchange = ccxt.kraken({'enableRateLimit': True})
    else:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    # Ensure rate limit enabled regardless of constructor arg
    exchange.enableRateLimit = True
    return exchange


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def chunk_filename(checkpoint_dir: str, exchange: str, symbol: str, start_ms: int, end_ms: int) -> str:
    safe_symbol = symbol.replace('/', '-')
    return os.path.join(
        checkpoint_dir,
        f"{exchange.upper()}_{safe_symbol}_{start_ms}_{end_ms}_trades.parquet",
    )


def save_trades_chunk(checkpoint_dir: str, exchange: str, symbol: str, trades: List[Dict]) -> Optional[str]:
    if not trades:
        return None
    start_ms = min(t['timestamp'] for t in trades if 'timestamp' in t and t['timestamp'] is not None)
    end_ms = max(t['timestamp'] for t in trades if 'timestamp' in t and t['timestamp'] is not None)
    filepath = chunk_filename(checkpoint_dir, exchange, symbol, start_ms, end_ms)
    df = pd.DataFrame(trades)
    # Normalize expected columns
    expected_cols = ['timestamp', 'price', 'amount']
    for col in expected_cols:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[expected_cols]
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, filepath)
    return filepath


class RecoverableExchangeError(Exception):
    pass


RECOVERABLE_EXCEPTIONS = (
    ccxt.NetworkError,
    ccxt.ExchangeNotAvailable,
    ccxt.RequestTimeout,
    ccxt.DDoSProtection,
    ccxt.RateLimitExceeded,
)


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type(RECOVERABLE_EXCEPTIONS),
)
def fetch_trades_page(
    exchange: ccxt.Exchange,
    symbol: str,
    since_ms: Optional[int] = None,
    limit: Optional[int] = None,
    params: Optional[Dict] = None,
):
    params = params or {}
    # ccxt fetch_trades generally moves forward in time using 'since'
    # Some exchanges support 'until'/'endTime'; we will page by 'since' forward per day window.
    return exchange.fetch_trades(symbol, since=since_ms, limit=limit, params=params)


def assemble_trades_from_checkpoints(checkpoint_dir: str, exchange: str, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    if not os.path.isdir(checkpoint_dir):
        return pd.DataFrame(columns=['timestamp', 'price', 'amount'])
    safe_symbol = symbol.replace('/', '-')
    rows: List[pd.DataFrame] = []
    for fname in os.listdir(checkpoint_dir):
        if not fname.endswith("_trades.parquet"):
            continue
        if not fname.startswith(f"{exchange.upper()}_{safe_symbol}_"):
            continue
        parts = fname.split('_')
        try:
            # ...EXCHANGE_SYMBOL_START_END_trades.parquet
            start_ms = int(parts[-3])
            end_ms = int(parts[-2])
        except Exception:
            continue
        if end_ms < int(start.timestamp() * 1000) or start_ms > int(end.timestamp() * 1000):
            continue
        path = os.path.join(checkpoint_dir, fname)
        try:
            table = pq.read_table(path)
            df = table.to_pandas()
            rows.append(df)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=['timestamp', 'price', 'amount'])
    df_all = pd.concat(rows, ignore_index=True)
    return df_all


def resample_to_1s_ohlcv(df_trades: pd.DataFrame) -> pd.DataFrame:
    if df_trades.empty:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    df = df_trades.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    ohlcv = df.resample('1S').agg({'price': 'ohlc', 'amount': 'sum'})
    # Flatten MultiIndex columns for OHLC
    ohlcv.columns = [
        'open' if c == ('price', 'open') else
        'high' if c == ('price', 'high') else
        'low' if c == ('price', 'low') else
        'close' if c == ('price', 'close') else
        'volume' for c in ohlcv.columns
    ]
    return ohlcv


def main():
    parser = argparse.ArgumentParser(description="Fetch historical trades and resample to 1s OHLCV Parquet")
    parser.add_argument('--config', type=str, default='config.json', help='Path to JSON configuration file')
    parser.add_argument('--exchange', help='Override exchange from config')
    parser.add_argument('--symbol', help='Override symbol from config')
    parser.add_argument('--start', help='Override UTC start datetime from config')
    parser.add_argument('--end', help='Override UTC end datetime from config')
    parser.add_argument('--chunk-hours', type=int, help='Override hours per fetch window from config')
    parser.add_argument('--checkpoint-dir', help='Override directory to store trade chunks from config')
    parser.add_argument('--resume', action='store_true', help='Override resume from existing checkpoints from config')
    parser.add_argument('--limit', type=int, help='Override per-request limit from config')
    parser.add_argument('--max-retries', type=int, help='Override max retries from config')
    parser.add_argument('--out', help='Override final Parquet output path from config')

    args = parser.parse_args()

    # Load config from file
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)
    
    # Helper to resolve config: command-line > config file > default
    def get_config_value(key, default=None):
        cli_value = getattr(args, key, None)
        if cli_value is not None:
            # Handle store_true action where default from config might be False
            if isinstance(cli_value, bool) and cli_value:
                return True
            if not isinstance(cli_value, bool):
                 return cli_value
        return config.get(key, default)

    # Resolve all parameters
    exchange_name = get_config_value('exchange')
    symbol = get_config_value('symbol')
    start_str = get_config_value('start')
    end_str = get_config_value('end')
    chunk_hours = get_config_value('chunk_hours', 24)
    checkpoint_dir = get_config_value('checkpoint_dir', 'checkpoints')
    resume = get_config_value('resume', False)
    limit = get_config_value('limit')
    max_retries = get_config_value('max_retries', 5)
    out_path = get_config_value('out')

    if not all([exchange_name, symbol, start_str, end_str, out_path]):
        print("Error: 'exchange', 'symbol', 'start', 'end', and 'out' must be defined in config or via command-line.")
        sys.exit(1)

    start_dt = parse_datetime_utc(start_str)
    end_dt = parse_datetime_utc(end_str)
    if end_dt <= start_dt:
        raise ValueError('end must be after start')

    ensure_dir(checkpoint_dir)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or '.'
    ensure_dir(out_dir)

    exchange = get_exchange(exchange_name)

    # Adjust retry policy dynamically
    global fetch_trades_page
    fetch_trades_page = retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=90),
        retry=retry_if_exception_type(RECOVERABLE_EXCEPTIONS),
    )(fetch_trades_page)

    # Many exchanges expect forward pagination via 'since'. We'll walk forward within each window.
    # Outer loop over backward windows for safe checkpointing.
    window_end = end_dt
    while window_end > start_dt:
        window_start = max(start_dt, window_end - timedelta(hours=chunk_hours))
        print(f"Fetching window: {window_start.isoformat()} -> {window_end.isoformat()}")

        # If resume, skip if we already have checkpoint coverage for this window
        if resume:
            existing = assemble_trades_from_checkpoints(checkpoint_dir, exchange_name, symbol, window_start, window_end)
            if not existing.empty:
                print("Existing checkpoints found for window; skipping fetch and keeping for consolidation")
                window_end = window_start
                continue
        
        # Fetch trades forward within the window
        since_ms = int(window_start.timestamp() * 1000)
        last_ts_ms = since_ms
        window_trades = []
        while True:
            try:
                trades = fetch_trades_page(exchange, symbol, since_ms=last_ts_ms, limit=limit)
            except RECOVERABLE_EXCEPTIONS as e:
                print(f"Recoverable error: {e}. Retrying...")
                continue
            except Exception as e:
                print(f"Unrecoverable error: {e}")
                raise
            if not trades:
                break
            
            # Normalize and add to window's trade list
            normalized = []
            for tr in trades:
                normalized.append({
                    'timestamp': tr.get('timestamp'),
                    'price': float(tr.get('price')) if tr.get('price') is not None else None,
                    'amount': float(tr.get('amount')) if tr.get('amount') is not None else None,
                })
            window_trades.extend(normalized)
            
            last_ts_ms = max(t['timestamp'] for t in normalized if t['timestamp'] is not None)
            # Move forward and avoid duplicates by +1 ms
            last_ts_ms += 1
            if last_ts_ms >= int(window_end.timestamp() * 1000):
                break
            # Respect rate limiting implicitly; small sleep to be nice
            time.sleep(exchange.rateLimit / 1000.0 if hasattr(exchange, 'rateLimit') else 0.2)
        
        if window_trades:
            save_trades_chunk(checkpoint_dir, exchange_name, symbol, window_trades)
            print(f"Saved checkpoint for window with {len(window_trades)} trades.")

        window_end = window_start

    # Consolidate all trades across checkpoints within entire range
    print("Consolidating checkpoints...")
    all_trades = assemble_trades_from_checkpoints(checkpoint_dir, exchange_name, symbol, start_dt, end_dt)
    if all_trades.empty:
        print("No trades collected. Exiting.")
        sys.exit(0)

    # Filter to range, drop NA and duplicates
    all_trades = all_trades.dropna(subset=['timestamp', 'price', 'amount'])
    all_trades['timestamp'] = all_trades['timestamp'].astype('int64')
    all_trades = all_trades[(all_trades['timestamp'] >= int(start_dt.timestamp() * 1000)) & (all_trades['timestamp'] < int(end_dt.timestamp() * 1000))]
    all_trades = all_trades.drop_duplicates()

    print(f"Total trades: {len(all_trades)}")
    ohlcv_1s = resample_to_1s_ohlcv(all_trades)

    # Save final parquet
    table = pa.Table.from_pandas(ohlcv_1s.reset_index(), preserve_index=False)
    pq.write_table(table, out_path)
    print(f"Saved 1s OHLCV to {out_path}")


if __name__ == '__main__':
    main()


