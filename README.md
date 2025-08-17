Historical Trades → 1s OHLCV (Parquet)

Overview
This project provides a robust, resumable Python script to fetch raw historical trade (tick) data from Binance, Coinbase, and Kraken using CCXT, then transform it into 1-second OHLCV bars with pandas, and store results as Parquet (pyarrow).

## Project Setup

### 1. Create a Virtual Environment (Recommended)
Using a virtual environment is a best practice to isolate project dependencies.

```bash
# Create a virtual environment named 'venv'
python -m venv venv

# Activate it
# On Windows
venv\\Scripts\\activate
# On macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

## How to Run

### 1. Configure Your Fetch Job
Edit the `config.json` file to define the parameters for your data fetch.

```json
{
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-02T00:00:00Z",
    "chunk_hours": 24,
    "checkpoint_dir": "checkpoints",
    "resume": true,
    "limit": 1000,
    "max_retries": 5,
    "out": "data/binance_btc-usdt_1s_ohlcv.parquet"
}
```

### 2. Run the Script
With your virtual environment activated and `config.json` set up, run the script:

```bash
python fetch_trades_ohlcv.py
```

### Overriding Configuration via Command-Line
You can override any setting from `config.json` using command-line arguments. This is useful for running quick, one-off jobs without modifying the file.

```bash
python fetch_trades_ohlcv.py --exchange kraken --symbol ETH/USD --start 2024-02-01 --end 2024-02-02 --out data/kraken_eth-usd_1s.parquet
```

## Verifying Data
After generating a Parquet file, you can verify its integrity using the `verify_data.py` script:

```bash
python verify_data.py data/binance_btc-usdt_1s_ohlcv.parquet
```

## Key Arguments (in `config.json` or CLI)
- `exchange`: one of `binance`, `coinbase`, `kraken`
- `symbol`: e.g., `BTC/USDT` (use `BTC/USD` for Coinbase/Kraken spot)
- `start`/`end`: ISO date or datetime (UTC). End is exclusive.
- `chunk_hours`: Window size for backward fetching (default `24`)
- `checkpoint_dir`: Where intermediate trade parquet chunks are stored
- `resume`: `true` to resume from existing checkpoints, `false` to fetch fresh
- `max_retries`: API retry attempts (default `5`)
- `out`: The final destination for the OHLCV Parquet file

## Outputs
- **Final OHLCV Parquet**: The file specified in the `out` parameter.
- **Intermediate Checkpoints**: Raw trade chunks stored in `checkpoint_dir` to allow for resumption.


