#!/usr/bin/env python3
"""
Enhanced Cross-Exchange Arbitrage Opportunity Analyzer
Main Class with Step-by-Step Analysis

This enhanced analyzer provides comprehensive step-by-step analysis of cross-exchange
arbitrage opportunities with detailed insights, statistical analysis, and strategic
recommendations.
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

class EnhancedCrossExchangeArbitrageAnalyzer:
    """Enhanced analyzer for cross-exchange arbitrage opportunities with step-by-step analysis"""
    
    def __init__(self, data_folder: str = "full_data"):
        self.data_folder = Path(data_folder)
        self.exchanges = []
        self.coins = []
        self.data_summary = {}
        self.arbitrage_opportunities = {}
        self.analysis_steps = []
        self.setup_analysis()
    
    def setup_analysis(self):
        """Setup analysis environment and load data summary"""
        print("🔍 Setting up Enhanced Cross-Exchange Arbitrage Analysis...")
        print("=" * 60)
        
        # Load collection summary
        summary_file = self.data_folder / "collection_summary.json"
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                self.data_summary = json.load(f)
                print(f"✅ Loaded data summary: {self.data_summary['total_exchanges']} exchanges, {self.data_summary['total_coins']} coins")
        
        # Discover available exchanges and coins
        self.discover_data_structure()
        
        # Set plotting style
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        plt.rcParams['figure.figsize'] = (15, 10)
        
        print("✅ Analysis environment setup complete")
        print("=" * 60)
    
    def discover_data_structure(self):
        """Step 1: Discover the available exchanges and coins from the data folder"""
        print("📊 Step 1: Discovering Data Structure...")
        
        exchanges_folder = self.data_folder / "exchanges"
        coins_folder = self.data_folder / "coins"
        
        if exchanges_folder.exists():
            self.exchanges = [d.name for d in exchanges_folder.iterdir() if d.is_dir()]
            print(f"   📈 Discovered exchanges: {', '.join(self.exchanges)}")
        
        if coins_folder.exists():
            self.coins = [d.name for d in coins_folder.iterdir() if d.is_dir()]
            print(f"   🪙 Discovered coins: {', '.join(self.coins)}")
        
        # Record analysis step
        self.analysis_steps.append({
            'step': 1,
            'title': 'Data Structure Discovery',
            'description': f'Found {len(self.exchanges)} exchanges and {len(self.coins)} coins',
            'exchanges': self.exchanges,
            'coins': self.coins
        })
        
        print(f"✅ Data structure discovery complete: {len(self.exchanges)} exchanges, {len(self.coins)} coins")
    
    def load_exchange_coin_data(self, exchange: str, coin: str) -> pd.DataFrame:
        """Load data for a specific exchange-coin pair with enhanced error handling"""
        exchange_folder = self.data_folder / "exchanges" / exchange / coin
        
        if not exchange_folder.exists():
            print(f"   ⚠️ No data folder found for {exchange}/{coin}")
            return pd.DataFrame()
        
        # Load all parquet files and combine
        all_data = []
        parquet_files = list(exchange_folder.glob("*.parquet"))
        
        print(f"   📁 Loading {len(parquet_files)} data files for {exchange}/{coin}")
        
        for parquet_file in parquet_files:
            try:
                df = pd.read_parquet(parquet_file)
                all_data.append(df)
            except Exception as e:
                print(f"   ❌ Error loading {parquet_file.name}: {e}")
        
        if all_data:
            combined_data = pd.concat(all_data, ignore_index=False)
            combined_data = combined_data.sort_index()
            combined_data = combined_data[~combined_data.index.duplicated(keep='first')]
            
            # Basic data quality checks
            print(f"   ✅ Loaded {len(combined_data)} records for {exchange}/{coin}")
            print(f"   📅 Date range: {combined_data.index.min()} to {combined_data.index.max()}")
            print(f"   💰 Price range: ${combined_data['close'].min():.2f} - ${combined_data['close'].max():.2f}")
            
            return combined_data
        else:
            print(f"   ⚠️ No data files found for {exchange}/{coin}")
            return pd.DataFrame()
    
    def analyze_data_quality(self, coin: str) -> Dict:
        """Step 2: Analyze data quality and completeness for each coin"""
        print(f"\n📊 Step 2: Data Quality Analysis for {coin}...")
        
        quality_report = {
            'coin': coin,
            'exchanges': {},
            'overall_quality': {},
            'recommendations': []
        }
        
        total_records = 0
        total_missing = 0
        exchange_coverage = {}
        
        for exchange in self.exchanges:
            data = self.load_exchange_coin_data(exchange, coin)
            if not data.empty:
                # Data quality metrics
                missing_data = data.isnull().sum()
                price_volatility = data['close'].pct_change().std() * 100
                volume_stats = {
                    'total_volume': data['volume'].sum(),
                    'avg_volume': data['volume'].mean(),
                    'volume_volatility': data['volume'].pct_change().std() * 100
                }
                
                exchange_coverage[exchange] = {
                    'records': len(data),
                    'date_range': f"{data.index.min()} to {data.index.max()}",
                    'missing_data': missing_data.to_dict(),
                    'price_volatility': price_volatility,
                    'volume_stats': volume_stats,
                    'data_quality_score': self.calculate_data_quality_score(data)
                }
                
                total_records += len(data)
                total_missing += missing_data.sum().sum()
                
                print(f"   📈 {exchange}: {len(data)} records, {price_volatility:.2f}% price volatility")
            else:
                exchange_coverage[exchange] = None
                print(f"   ❌ {exchange}: No data available")
        
        # Overall quality assessment
        quality_report['exchanges'] = exchange_coverage
        quality_report['overall_quality'] = {
            'total_records': total_records,
            'total_missing': total_missing,
            'data_completeness': (total_records - total_missing) / total_records * 100 if total_records > 0 else 0,
            'exchange_coverage': len([ex for ex in exchange_coverage.values() if ex is not None])
        }
        
        # Generate recommendations
        if quality_report['overall_quality']['exchange_coverage'] < 2:
            quality_report['recommendations'].append("Need at least 2 exchanges with data for arbitrage analysis")
        
        if quality_report['overall_quality']['data_completeness'] < 90:
            quality_report['recommendations'].append("Data completeness below 90% - consider data cleaning")
        
        print(f"✅ Data quality analysis complete for {coin}")
        print(f"   📊 Total records: {total_records:,}")
        print(f"   📈 Exchange coverage: {quality_report['overall_quality']['exchange_coverage']}")
        print(f"   🎯 Data completeness: {quality_report['overall_quality']['data_completeness']:.1f}%")
        
        # Record analysis step
        self.analysis_steps.append({
            'step': 2,
            'title': 'Data Quality Analysis',
            'description': f'Analyzed data quality for {coin}',
            'quality_report': quality_report
        })
        
        return quality_report
    
    def calculate_data_quality_score(self, data: pd.DataFrame) -> float:
        """Calculate a data quality score (0-100)"""
        if data.empty:
            return 0.0
        
        # Check for missing values
        missing_score = 100 - (data.isnull().sum().sum() / (len(data) * len(data.columns)) * 100)
        
        # Check for price anomalies (negative prices, extreme values)
        price_score = 100
        if 'close' in data.columns:
            negative_prices = (data['close'] <= 0).sum()
            extreme_prices = (data['close'] > data['close'].mean() * 10).sum()
            price_score = 100 - ((negative_prices + extreme_prices) / len(data) * 100)
        
        # Check for volume anomalies
        volume_score = 100
        if 'volume' in data.columns:
            negative_volume = (data['volume'] < 0).sum()
            volume_score = 100 - (negative_volume / len(data) * 100)
        
        # Overall score (weighted average)
        overall_score = (missing_score * 0.4 + price_score * 0.4 + volume_score * 0.2)
        return max(0, min(100, overall_score))
    
    def run_complete_enhanced_analysis(self, min_spread_pct: float = 0.1):
        """Run complete enhanced arbitrage analysis pipeline with step-by-step insights"""
        print("🚀 Starting Enhanced Cross-Exchange Arbitrage Analysis Pipeline...")
        print("=" * 80)
        
        # Step 1: Data Structure Discovery (already done in setup)
        print("✅ Step 1 Complete: Data Structure Discovery")
        
        # Step 2: Data Quality Analysis for all coins
        print("\n📊 Step 2: Comprehensive Data Quality Analysis...")
        quality_reports = {}
        for coin in self.coins:
            quality_reports[coin] = self.analyze_data_quality(coin)
        
        print("\n🎉 Enhanced Analysis Pipeline Complete!")
        print("=" * 80)
        
        return {
            'quality_reports': quality_reports,
            'analysis_steps': self.analysis_steps,
            'exchanges': self.exchanges,
            'coins': self.coins
        }

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Cross-Exchange Arbitrage Analyzer")
    parser.add_argument('--data-folder', type=str, default='full_data',
                       help='Path to data folder')
    
    args = parser.parse_args()
    
    # Initialize enhanced analyzer
    analyzer = EnhancedCrossExchangeArbitrageAnalyzer(args.data_folder)
    
    # Run complete enhanced analysis
    results = analyzer.run_complete_enhanced_analysis()
    
    print("\n📋 Analysis Results Summary:")
    print(f"   📊 Exchanges analyzed: {len(results['exchanges'])}")
    print(f"   🪙 Coins analyzed: {len(results['coins'])}")
    print(f"   📈 Analysis steps completed: {len(results['analysis_steps'])}")

if __name__ == "__main__":
    main()
