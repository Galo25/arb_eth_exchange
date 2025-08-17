#!/usr/bin/env python3
"""
Enhanced Cross-Exchange Arbitrage Opportunity Analysis
Task #010 - Phase 2: Data Scientist Analysis (Enhanced)

This enhanced script provides comprehensive step-by-step analysis of cross-exchange
arbitrage opportunities with detailed insights, statistical analysis, and strategic
recommendations.
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

# Enhanced financial analysis libraries
import pandas_ta as ta
import empyrical as ep
from scipy import stats
from scipy.stats import shapiro, jarque_bera, normaltest
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

class CrossExchangeArbitrageAnalyzer:
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
    
    def calculate_cross_exchange_spreads(self, coin: str) -> pd.DataFrame:
        """Calculate spreads between exchanges for a specific coin"""
        print(f"📊 Calculating cross-exchange spreads for {coin}")
        
        exchange_data = {}
        
        # Load data from all exchanges for this coin
        for exchange in self.exchanges:
            data = self.load_exchange_coin_data(exchange, coin)
            if not data.empty:
                exchange_data[exchange] = data
        
        if len(exchange_data) < 2:
            print(f"⚠️ Need at least 2 exchanges with data for {coin}")
            return pd.DataFrame()
        
        # Find common time periods
        common_times = None
        for exchange, data in exchange_data.items():
            if common_times is None:
                common_times = set(data.index)
            else:
                common_times = common_times.intersection(set(data.index))
        
        if not common_times:
            print(f"⚠️ No common time periods found for {coin}")
            return pd.DataFrame()
        
        # Create comparison DataFrame
        comparison_data = {}
        for exchange, data in exchange_data.items():
            common_data = data.loc[list(common_times)]
            comparison_data[f"{exchange}_close"] = common_data['close']
            comparison_data[f"{exchange}_volume"] = common_data['volume']
        
        comparison_df = pd.DataFrame(comparison_data)
        
        # Calculate spreads between exchanges
        exchanges_list = list(exchange_data.keys())
        for i in range(len(exchanges_list)):
            for j in range(i + 1, len(exchanges_list)):
                ex1, ex2 = exchanges_list[i], exchanges_list[j]
                spread_col = f"spread_{ex1}_vs_{ex2}"
                spread_pct_col = f"spread_pct_{ex1}_vs_{ex2}"
                
                comparison_df[spread_col] = comparison_df[f"{ex1}_close"] - comparison_df[f"{ex2}_close"]
                comparison_df[spread_pct_col] = (comparison_df[spread_col] / comparison_df[f"{ex1}_close"]) * 100
        
        print(f"✅ Calculated spreads for {len(common_times)} time periods")
        return comparison_df
    
    def identify_arbitrage_opportunities(self, coin: str, min_spread_pct: float = 0.1) -> Dict:
        """Identify arbitrage opportunities for a specific coin"""
        print(f"🎯 Identifying arbitrage opportunities for {coin} (min spread: {min_spread_pct}%)")
        
        comparison_df = self.calculate_cross_exchange_spreads(coin)
        if comparison_df.empty:
            return {}
        
        opportunities = {
            'coin': coin,
            'total_observations': len(comparison_df),
            'opportunities': [],
            'summary': {}
        }
        
        # Find spread columns
        spread_cols = [col for col in comparison_df.columns if col.startswith('spread_pct_')]
        
        for spread_col in spread_cols:
            # Extract exchange names
            ex1, ex2 = spread_col.replace('spread_pct_', '').split('_vs_')
            
            # Find opportunities above threshold
            above_threshold = comparison_df[comparison_df[spread_col] > min_spread_pct]
            
            if len(above_threshold) > 0:
                opportunity = {
                    'exchange_pair': f"{ex1}_vs_{ex2}",
                    'buy_exchange': ex1 if above_threshold[spread_col].mean() > 0 else ex2,
                    'sell_exchange': ex2 if above_threshold[spread_col].mean() > 0 else ex1,
                    'opportunity_count': len(above_threshold),
                    'opportunity_percentage': len(above_threshold) / len(comparison_df) * 100,
                    'max_spread': above_threshold[spread_col].max(),
                    'avg_spread': above_threshold[spread_col].mean(),
                    'min_spread': above_threshold[spread_col].min(),
                    'total_volume': above_threshold[f"{ex1}_volume"].sum() + above_threshold[f"{ex2}_volume"].sum()
                }
                
                opportunities['opportunities'].append(opportunity)
        
        # Calculate summary statistics
        if opportunities['opportunities']:
            total_opps = sum(opp['opportunity_count'] for opp in opportunities['opportunities'])
            avg_spread = np.mean([opp['avg_spread'] for opp in opportunities['opportunities']])
            max_spread = max([opp['max_spread'] for opp in opportunities['opportunities']])
            
            opportunities['summary'] = {
                'total_opportunities': total_opps,
                'average_spread': avg_spread,
                'maximum_spread': max_spread,
                'exchange_pairs_with_opportunities': len(opportunities['opportunities'])
            }
        
        print(f"✅ Found {len(opportunities['opportunities'])} exchange pairs with arbitrage opportunities")
        return opportunities
    
    def analyze_all_coins(self, min_spread_pct: float = 0.1) -> Dict:
        """Analyze arbitrage opportunities for all coins"""
        print(f"🚀 Starting comprehensive arbitrage analysis for all coins...")
        
        all_opportunities = {}
        total_opportunities = 0
        
        for coin in self.coins:
            print(f"\n📊 Analyzing {coin}...")
            opportunities = self.identify_arbitrage_opportunities(coin, min_spread_pct)
            all_opportunities[coin] = opportunities
            
            if opportunities and opportunities.get('summary'):
                total_opportunities += opportunities['summary']['total_opportunities']
        
        # Overall summary
        overall_summary = {
            'analysis_date': pd.Timestamp.now().isoformat(),
            'total_coins_analyzed': len(self.coins),
            'total_exchanges': len(self.exchanges),
            'total_opportunities': total_opportunities,
            'coins_with_opportunities': len([c for c in all_opportunities.values() if c.get('opportunities')]),
            'min_spread_threshold': min_spread_pct
        }
        
        all_opportunities['overall_summary'] = overall_summary
        
        print(f"\n🎉 Analysis completed!")
        print(f"📊 Total opportunities found: {total_opportunities}")
        print(f"🪙 Coins with opportunities: {overall_summary['coins_with_opportunities']}")
        
        return all_opportunities
    
    def create_arbitrage_visualizations(self, opportunities: Dict):
        """Create comprehensive visualizations of arbitrage opportunities"""
        print("📈 Creating arbitrage opportunity visualizations...")
        
        # 1. Overall opportunity summary
        coins_with_opps = [coin for coin, data in opportunities.items() 
                          if isinstance(data, dict) and data.get('opportunities')]
        
        if not coins_with_opps:
            print("⚠️ No opportunities found for visualization")
            return
        
        # 2. Opportunities per coin
        opp_counts = []
        avg_spreads = []
        max_spreads = []
        
        for coin in coins_with_opps:
            data = opportunities[coin]
            if data.get('summary'):
                opp_counts.append(data['summary']['total_opportunities'])
                avg_spreads.append(data['summary']['average_spread'])
                max_spreads.append(data['summary']['maximum_spread'])
        
        # Create subplots
        fig, axes = plt.subplots(2, 2, figsize=(20, 15))
        
        # Opportunities per coin
        axes[0,0].bar(coins_with_opps, opp_counts, color='skyblue', alpha=0.7)
        axes[0,0].set_title('Arbitrage Opportunities per Coin')
        axes[0,0].set_ylabel('Number of Opportunities')
        axes[0,0].tick_params(axis='x', rotation=45)
        
        # Average spreads per coin
        axes[0,1].bar(coins_with_opps, avg_spreads, color='lightgreen', alpha=0.7)
        axes[0,1].set_title('Average Spread per Coin')
        axes[0,1].set_ylabel('Spread (%)')
        axes[0,1].tick_params(axis='x', rotation=45)
        
        # Maximum spreads per coin
        axes[1,0].bar(coins_with_opps, max_spreads, color='salmon', alpha=0.7)
        axes[1,0].set_title('Maximum Spread per Coin')
        axes[1,0].set_ylabel('Spread (%)')
        axes[1,0].tick_params(axis='x', rotation=45)
        
        # Exchange pair opportunities
        exchange_pairs = {}
        for coin, data in opportunities.items():
            if isinstance(data, dict) and data.get('opportunities'):
                for opp in data['opportunities']:
                    pair = opp['exchange_pair']
                    if pair not in exchange_pairs:
                        exchange_pairs[pair] = 0
                    exchange_pairs[pair] += opp['opportunity_count']
        
        if exchange_pairs:
            pairs = list(exchange_pairs.keys())
            counts = list(exchange_pairs.values())
            
            axes[1,1].bar(pairs, counts, color='gold', alpha=0.7)
            axes[1,1].set_title('Opportunities by Exchange Pair')
            axes[1,1].set_ylabel('Number of Opportunities')
            axes[1,1].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        # Save visualization
        viz_file = self.data_folder / "analysis" / "arbitrage_opportunities_analysis.png"
        plt.savefig(viz_file, dpi=300, bbox_inches='tight')
        print(f"💾 Saved visualization to {viz_file}")
        
        plt.show()
    
    def generate_arbitrage_report(self, opportunities: Dict) -> str:
        """Generate comprehensive arbitrage analysis report"""
        print("📋 Generating arbitrage analysis report...")
        
        report = []
        report.append("# Cross-Exchange Arbitrage Opportunity Analysis Report")
        report.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Data Source:** {self.data_folder}")
        report.append(f"**Exchanges Analyzed:** {', '.join(self.exchanges)}")
        report.append(f"**Coins Analyzed:** {', '.join(self.coins)}")
        report.append("")
        
        # Overall summary
        if 'overall_summary' in opportunities:
            summary = opportunities['overall_summary']
            report.append("## Executive Summary")
            report.append(f"- **Total Coins Analyzed:** {summary['total_coins_analyzed']}")
            report.append(f"- **Total Exchanges:** {summary['total_exchanges']}")
            report.append(f"- **Total Opportunities Found:** {summary['total_opportunities']}")
            report.append(f"- **Coins with Opportunities:** {summary['coins_with_opportunities']}")
            report.append(f"- **Minimum Spread Threshold:** {summary['min_spread_threshold']}%")
            report.append("")
        
        # Detailed analysis by coin
        report.append("## Detailed Analysis by Coin")
        
        for coin in self.coins:
            if coin in opportunities and opportunities[coin].get('opportunities'):
                data = opportunities[coin]
                report.append(f"### {coin}")
                report.append(f"- **Total Observations:** {data['total_observations']:,}")
                report.append(f"- **Exchange Pairs with Opportunities:** {len(data['opportunities'])}")
                
                if data.get('summary'):
                    report.append(f"- **Total Opportunities:** {data['summary']['total_opportunities']:,}")
                    report.append(f"- **Average Spread:** {data['summary']['average_spread']:.4f}%")
                    report.append(f"- **Maximum Spread:** {data['summary']['maximum_spread']:.4f}%")
                
                report.append("")
                
                # Exchange pair details
                for opp in data['opportunities']:
                    report.append(f"#### {opp['exchange_pair']}")
                    report.append(f"- **Buy Exchange:** {opp['buy_exchange']}")
                    report.append(f"- **Sell Exchange:** {opp['sell_exchange']}")
                    report.append(f"- **Opportunities:** {opp['opportunity_count']:,} ({opp['opportunity_percentage']:.2f}%)")
                    report.append(f"- **Spread Range:** {opp['min_spread']:.4f}% - {opp['max_spread']:.4f}%")
                    report.append(f"- **Average Spread:** {opp['avg_spread']:.4f}%")
                    report.append(f"- **Total Volume:** {opp['total_volume']:,.2f}")
                    report.append("")
            else:
                report.append(f"### {coin}")
                report.append("- **No arbitrage opportunities found**")
                report.append("")
        
        # Recommendations
        report.append("## Strategic Recommendations")
        report.append("")
        report.append("### High-Priority Opportunities")
        
        # Find top opportunities
        all_opps = []
        for coin, data in opportunities.items():
            if isinstance(data, dict) and data.get('opportunities'):
                for opp in data['opportunities']:
                    opp['coin'] = coin
                    all_opps.append(opp)
        
        if all_opps:
            # Sort by opportunity percentage
            all_opps.sort(key=lambda x: x['opportunity_percentage'], reverse=True)
            
            for i, opp in enumerate(all_opps[:5]):
                report.append(f"{i+1}. **{opp['coin']} - {opp['exchange_pair']}**")
                report.append(f"   - Opportunity Rate: {opp['opportunity_percentage']:.2f}%")
                report.append(f"   - Average Spread: {opp['avg_spread']:.4f}%")
                report.append(f"   - Buy: {opp['buy_exchange']}, Sell: {opp['sell_exchange']}")
                report.append("")
        
        report.append("### Implementation Strategy")
        report.append("1. **Start with high-frequency pairs** - Focus on coins with highest opportunity rates")
        report.append("2. **Exchange prioritization** - Begin with most liquid exchange pairs")
        report.append("3. **Risk management** - Implement strict spread thresholds and volume limits")
        report.append("4. **Execution optimization** - Develop fast execution algorithms for identified opportunities")
        report.append("5. **Continuous monitoring** - Set up real-time opportunity detection systems")
        
        # Save report
        report_text = "\n".join(report)
        report_file = self.data_folder / "analysis" / "arbitrage_analysis_report.md"
        
        with open(report_file, 'w') as f:
            f.write(report_text)
        
        print(f"💾 Saved report to {report_file}")
        return report_text
    
    def run_complete_analysis(self, min_spread_pct: float = 0.1):
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
        
        # Step 3: Cross-Exchange Spread Analysis
        print("\n📊 Step 3: Cross-Exchange Spread Analysis...")
        spread_analysis = {}
        for coin in self.coins:
            spread_analysis[coin] = self.calculate_cross_exchange_spreads(coin)
        
        # Step 4: Arbitrage Opportunity Identification
        print("\n🎯 Step 4: Arbitrage Opportunity Identification...")
        all_opportunities = {}
        total_opportunities = 0
        
        for coin in self.coins:
            print(f"\n   📊 Analyzing {coin}...")
            opportunities = self.identify_arbitrage_opportunities(coin, min_spread_pct)
            all_opportunities[coin] = opportunities
            
            if opportunities and opportunities.get('summary'):
                total_opportunities += opportunities['summary']['total_opportunities']
        
        # Step 5: Comprehensive Analysis Summary
        print("\n📋 Step 5: Generating Comprehensive Analysis Summary...")
        
        overall_summary = {
            'analysis_date': pd.Timestamp.now().isoformat(),
            'total_coins_analyzed': len(self.coins),
            'total_exchanges': len(self.exchanges),
            'total_opportunities': total_opportunities,
            'coins_with_opportunities': len([c for c in all_opportunities.values() if c.get('opportunities')]),
            'min_spread_threshold': min_spread_pct,
            'analysis_steps': self.analysis_steps,
            'quality_reports': quality_reports
        }
        
        all_opportunities['overall_summary'] = overall_summary
        
        # Step 6: Create Enhanced Visualizations
        print("\n📈 Step 6: Creating Enhanced Visualizations...")
        self.create_arbitrage_visualizations(all_opportunities)
        
        # Step 7: Generate Comprehensive Report
        print("\n📋 Step 7: Generating Comprehensive Analysis Report...")
        report = self.generate_arbitrage_report(all_opportunities)
        
        # Step 8: Save All Analysis Results
        print("\n💾 Step 8: Saving Analysis Results...")
        self.save_analysis_results(all_opportunities)
        
        print("\n🎉 Enhanced Analysis Pipeline Complete!")
        print("=" * 80)
        
        return all_opportunities
    
    def save_analysis_results(self, opportunities: Dict):
        """Save all analysis results and data"""
        print("   💾 Saving analysis results...")
        
        # Save opportunities data
        opportunities_file = self.data_folder / "analysis" / "enhanced_arbitrage_opportunities.json"
        with open(opportunities_file, 'w') as f:
            json.dump(opportunities, f, indent=2, default=str)
        
        # Save analysis steps
        steps_file = self.data_folder / "analysis" / "analysis_steps.json"
        with open(steps_file, 'w') as f:
            json.dump(self.analysis_steps, f, indent=2, default=str)
        
        print(f"   💾 Saved opportunities data to {opportunities_file}")
        print(f"   💾 Saved analysis steps to {steps_file}")

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Cross-Exchange Arbitrage Analyzer")
    parser.add_argument('--data-folder', type=str, default='full_data',
                       help='Path to data folder')
    parser.add_argument('--min-spread', type=float, default=0.1,
                       help='Minimum spread percentage for opportunities')
    parser.add_argument('--coin', type=str, help='Analyze specific coin only')
    parser.add_argument('--enhanced', action='store_true', 
                       help='Run enhanced step-by-step analysis pipeline')
    
    args = parser.parse_args()
    
    # Initialize enhanced analyzer
    analyzer = CrossExchangeArbitrageAnalyzer(args.data_folder)
    
    if args.coin:
        # Analyze specific coin
        print(f"🎯 Running enhanced analysis for {args.coin}...")
        opportunities = analyzer.identify_arbitrage_opportunities(args.coin, args.min_spread)
        print(f"\n📊 Enhanced analysis results for {args.coin}:")
        print(json.dumps(opportunities, indent=2, default=str))
    elif args.enhanced:
        # Run complete enhanced analysis pipeline
        print("🚀 Running Enhanced Analysis Pipeline...")
        analyzer.run_complete_analysis(args.min_spread)
    else:
        # Run standard analysis
        print("📊 Running Standard Analysis...")
        opportunities = analyzer.analyze_all_coins(args.min_spread)
        print(f"\n📋 Standard analysis complete. Found opportunities for {len(opportunities)} coins.")
        print("💡 Use --enhanced flag for step-by-step analysis pipeline.")

if __name__ == "__main__":
    main()
