#!/usr/bin/env python3
"""
Multi-Coin Multi-Exchange Data Collection System
Task #010 - Comprehensive arbitrage data collection

This script fetches historical market data for top cryptocurrencies across major exchanges
to enable cross-exchange arbitrage analysis and strategy development.
"""

import os
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
import ccxt
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MultiCoinDataCollector:
    """Comprehensive data collector for multiple coins across multiple exchanges"""
    
    def __init__(self, config_path: str = "multi_coin_config.json", test_mode: bool = False):
        self.config = self.load_config(config_path)
        self.test_mode = test_mode
        self.exchanges = {}
        self.setup_exchanges()
        self.setup_folders()
        
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"Loaded configuration from {config_path}")
        else:
            config = self.create_default_config()
            self.save_config(config, config_path)
            logger.info(f"Created default configuration at {config_path}")
        return config
    
    def create_default_config(self) -> Dict:
        """Create default configuration for multi-coin data collection"""
        return {
            "exchanges": {
                "binance": {
                    "enabled": True,
                    "api_key": "",
                    "secret": "",
                    "sandbox": False
                },
                "kraken": {
                    "enabled": True,
                    "api_key": "",
                    "secret": "",
                    "sandbox": False
                },
                "coinbase": {
                    "enabled": False,  # Disabled for faster testing
                    "api_key": "",
                    "secret": "",
                    "sandbox": False
                },
                "kucoin": {
                    "enabled": False,  # Disabled for faster testing
                    "api_key": "",
                    "secret": "",
                    "sandbox": False
                },
                "okx": {
                    "enabled": False,  # Disabled for faster testing
                    "api_key": "",
                    "secret": "",
                    "sandbox": False
                }
            },
            "coins": [
                "BTC/USDT",
                "ETH/USDT", 
                "BNB/USDT",
                "ADA/USDT",
                "SOL/USDT",
                "DOT/USDT",
                "MATIC/USDT",
                "LINK/USDT",
                "UNI/USDT",
                "AVAX/USDT"
            ],
            "data_settings": {
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-08-01T00:00:00Z",
                "chunk_hours": 24,
                "limit": 1000,
                "max_retries": 5,
                "rate_limit_delay": 0.1
            },
            "output_settings": {
                "base_folder": "full_data",
                "parquet_compression": "snappy",
                "checkpoint_interval": 1000
            }
        }
    
    def save_config(self, config: Dict, config_path: str):
        """Save configuration to JSON file"""
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setup_exchanges(self):
        """Initialize exchange connections"""
        connected_count = 0
        max_exchanges = 2 if self.test_mode else 999  # Limit to 2 exchanges in test mode
        
        for exchange_name, exchange_config in self.config["exchanges"].items():
            if not exchange_config.get("enabled", True):
                continue
                
            if connected_count >= max_exchanges:
                logger.info(f"⏸️ Skipping {exchange_name} (test mode limit: {max_exchanges} exchanges)")
                continue
                
            try:
                exchange_class = getattr(ccxt, exchange_name)
                exchange = exchange_class({
                    'apiKey': exchange_config.get('api_key', ''),
                    'secret': exchange_config.get('secret', ''),
                    'sandbox': exchange_config.get('sandbox', False),
                    'enableRateLimit': True,
                    'rateLimit': int(1 / self.config['data_settings']['rate_limit_delay'] * 1000)
                })
                
                # Test connection
                exchange.load_markets()
                self.exchanges[exchange_name] = exchange
                connected_count += 1
                logger.info(f"✅ Connected to {exchange_name} ({connected_count}/{max_exchanges})")
                
            except Exception as e:
                logger.error(f"❌ Failed to connect to {exchange_name}: {e}")
                continue
    
    def setup_folders(self):
        """Create organized folder structure"""
        base_folder = Path(self.config["output_settings"]["base_folder"])
        
        # Create main folders
        folders = [
            base_folder / "exchanges",
            base_folder / "coins", 
            base_folder / "analysis",
            base_folder / "checkpoints",
            base_folder / "logs"
        ]
        
        for folder in folders:
            folder.mkdir(exist_ok=True)
            logger.info(f"📁 Created folder: {folder}")
        
        # Create exchange-specific folders
        for exchange_name in self.exchanges.keys():
            exchange_folder = base_folder / "exchanges" / exchange_name
            exchange_folder.mkdir(exist_ok=True)
            
            # Create coin-specific folders within each exchange
            for coin in self.config["coins"]:
                coin_folder = exchange_folder / coin.replace("/", "_")
                coin_folder.mkdir(exist_ok=True)
        
        # Create coin-specific folders
        for coin in self.config["coins"]:
            coin_folder = base_folder / "coins" / coin.replace("/", "_")
            coin_folder.mkdir(exist_ok=True)
    
    def get_exchange_symbol(self, exchange_name: str, coin: str) -> Optional[str]:
        """Get the correct symbol format for a specific exchange"""
        try:
            exchange = self.exchanges[exchange_name]
            markets = exchange.load_markets()
            
            # Try different symbol formats
            symbol_variants = [
                coin,
                coin.replace("/", ""),
                coin.replace("/", "-"),
                coin.replace("USDT", "USD"),
                coin.replace("USDT", "USDT")
            ]
            
            for variant in symbol_variants:
                if variant in markets:
                    return variant
            
            logger.warning(f"⚠️ Symbol {coin} not found in {exchange_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting symbol for {coin} on {exchange_name}: {e}")
            return None
    
    def fetch_trades_chunk(self, exchange_name: str, coin: str, since: int, limit: int) -> List[Dict]:
        """Fetch a chunk of trades from an exchange"""
        exchange = self.exchanges[exchange_name]
        symbol = self.get_exchange_symbol(exchange_name, coin)
        
        if not symbol:
            return []
        
        try:
            trades = exchange.fetch_trades(symbol, since=since, limit=limit)
            return trades
        except Exception as e:
            logger.error(f"❌ Error fetching trades from {exchange_name} for {coin}: {e}")
            return []
    
    def process_trades_to_ohlcv(self, trades: List[Dict], timeframe: str = '1s') -> pd.DataFrame:
        """Convert raw trades to OHLCV data"""
        if not trades:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(trades)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Resample to 1-second OHLCV
        ohlcv = df['price'].resample('1s').ohlc()
        ohlcv['volume'] = df['amount'].resample('1s').sum()
        
        # Forward fill missing values
        ohlcv = ohlcv.ffill()
        
        return ohlcv
    
    def save_data_chunk(self, exchange_name: str, coin: str, data: pd.DataFrame, 
                        start_time: datetime, end_time: datetime):
        """Save data chunk to organized folder structure"""
        if data.empty:
            return
        
        # Create filename
        coin_clean = coin.replace("/", "_")
        start_str = start_time.strftime("%Y%m%d_%H%M%S")
        end_str = end_time.strftime("%Y%m%d_%H%M%S")
        
        filename = f"{exchange_name}_{coin_clean}_{start_str}_to_{end_str}.parquet"
        
        # Save to exchange-specific folder
        exchange_folder = Path(self.config["output_settings"]["base_folder"]) / "exchanges" / exchange_name / coin_clean
        filepath = exchange_folder / filename
        
        # Save to coin-specific folder
        coin_folder = Path(self.config["output_settings"]["base_folder"]) / "coins" / coin_clean
        coin_filepath = coin_folder / filename
        
        try:
            # Save with compression
            compression = self.config["output_settings"]["parquet_compression"]
            data.to_parquet(filepath, compression=compression, engine='pyarrow')
            data.to_parquet(coin_filepath, compression=compression, engine='pyarrow')
            
            logger.info(f"💾 Saved {len(data)} records to {filepath}")
            
        except Exception as e:
            logger.error(f"❌ Error saving data: {e}")
    
    def collect_data_for_pair(self, exchange_name: str, coin: str):
        """Collect data for a specific exchange-coin pair"""
        logger.info(f"🚀 Starting data collection for {coin} on {exchange_name}")
        
        # Parse dates
        start_date = datetime.fromisoformat(self.config["data_settings"]["start_date"].replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(self.config["data_settings"]["end_date"].replace('Z', '+00:00'))
        
        current_time = start_date.replace(tzinfo=None)
        end_date = end_date.replace(tzinfo=None)
        chunk_hours = self.config["data_settings"]["chunk_hours"]
        limit = self.config["data_settings"]["limit"]
        max_retries = self.config["data_settings"]["max_retries"]
        
        total_records = 0
        
        while current_time < end_date:
            chunk_end = min(current_time + timedelta(hours=chunk_hours), end_date)
            
            # Convert to timestamp
            since = int(current_time.timestamp() * 1000)
            
            # Fetch data with retries
            trades = []
            for attempt in range(max_retries):
                try:
                    trades = self.fetch_trades_chunk(exchange_name, coin, since, limit)
                    if trades:
                        break
                    time.sleep(self.config["data_settings"]["rate_limit_delay"])
                except Exception as e:
                    logger.warning(f"⚠️ Attempt {attempt + 1} failed for {coin} on {exchange_name}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                    continue
            
            if trades:
                # Process to OHLCV
                ohlcv_data = self.process_trades_to_ohlcv(trades)
                
                if not ohlcv_data.empty:
                    # Save chunk
                    self.save_data_chunk(exchange_name, coin, ohlcv_data, current_time, chunk_end)
                    total_records += len(ohlcv_data)
                
                # Update time for next iteration
                if len(trades) < limit:
                    # Less data than limit, move to next chunk
                    current_time = chunk_end
                else:
                    # Use last trade timestamp
                    last_trade_time = pd.to_datetime(trades[-1]['timestamp'], unit='ms')
                    current_time = last_trade_time
            else:
                # No trades, move to next chunk
                current_time = chunk_end
            
            # Rate limiting
            time.sleep(self.config["data_settings"]["rate_limit_delay"])
        
        logger.info(f"✅ Completed {coin} on {exchange_name}: {total_records} total records")
        return total_records
    
    def run_full_collection(self):
        """Run data collection for all enabled exchange-coin pairs"""
        logger.info("🚀 Starting comprehensive multi-coin multi-exchange data collection")
        
        total_pairs = len(self.exchanges) * len(self.config["coins"])
        completed_pairs = 0
        
        collection_summary = {}
        
        for exchange_name in self.exchanges.keys():
            collection_summary[exchange_name] = {}
            
            for coin in self.config["coins"]:
                try:
                    logger.info(f"📊 Processing {exchange_name} - {coin} ({completed_pairs + 1}/{total_pairs})")
                    
                    records = self.collect_data_for_pair(exchange_name, coin)
                    collection_summary[exchange_name][coin] = records
                    
                    completed_pairs += 1
                    
                except Exception as e:
                    logger.error(f"❌ Failed to collect data for {coin} on {exchange_name}: {e}")
                    collection_summary[exchange_name][coin] = 0
        
        # Save collection summary
        self.save_collection_summary(collection_summary)
        
        logger.info("🎉 Data collection completed!")
        return collection_summary
    
    def save_collection_summary(self, summary: Dict):
        """Save collection summary to file"""
        summary_file = Path(self.config["output_settings"]["base_folder"]) / "collection_summary.json"
        
        summary_data = {
            "collection_date": datetime.now().isoformat(),
            "total_exchanges": len(self.exchanges),
            "total_coins": len(self.config["coins"]),
            "total_pairs": len(self.exchanges) * len(self.config["coins"]),
            "summary": summary
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        logger.info(f"📋 Collection summary saved to {summary_file}")

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Multi-Coin Multi-Exchange Data Collector")
    parser.add_argument('--config', type=str, default='multi_coin_config.json',
                       help='Path to configuration file')
    parser.add_argument('--exchange', type=str, help='Specific exchange to collect from')
    parser.add_argument('--coin', type=str, help='Specific coin to collect')
    parser.add_argument('--test', action='store_true', help='Run in test mode with limited data')
    
    args = parser.parse_args()
    
    # Initialize collector
    collector = MultiCoinDataCollector(args.config, test_mode=args.test)
    
    if args.test:
        logger.info("🧪 Running in test mode")
        # Test with just one pair
        test_exchange = list(collector.exchanges.keys())[0]
        test_coin = collector.config["coins"][0]
        collector.collect_data_for_pair(test_exchange, test_coin)
    elif args.exchange and args.coin:
        # Collect specific pair
        collector.collect_data_for_pair(args.exchange, args.coin)
    else:
        # Full collection
        collector.run_full_collection()

if __name__ == "__main__":
    main()
