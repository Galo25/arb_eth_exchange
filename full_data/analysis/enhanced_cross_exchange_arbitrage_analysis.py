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
        """Discover the available exchanges and coins from the data folder"""
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
    
    def calculate_cross_exchange_spreads(self, coin: str) -> pd.DataFrame:
        """Step 3: Calculate detailed spreads between exchanges for a specific coin"""
        print(f"\n📊 Step 3: Cross-Exchange Spread Analysis for {coin}...")
        
        exchange_data = {}
        
        # Load data from all exchanges for this coin
        for exchange in self.exchanges:
            data = self.load_exchange_coin_data(exchange, coin)
            if not data.empty:
                exchange_data[exchange] = data
        
        if len(exchange_data) < 2:
            print(f"   ⚠️ Need at least 2 exchanges with data for {coin}")
            return pd.DataFrame()
        
        # Find common time periods
        common_times = None
        for exchange, data in exchange_data.items():
            if common_times is None:
                common_times = set(data.index)
            else:
                common_times = common_times.intersection(set(data.index))
        
        if not common_times:
            print(f"   ⚠️ No common time periods found for {coin}")
            return pd.DataFrame()
        
        print(f"   📅 Found {len(common_times)} common time periods")
        
        # Create comparison DataFrame
        comparison_data = {}
        for exchange, data in exchange_data.items():
            common_data = data.loc[list(common_times)]
            comparison_data[f"{exchange}_close"] = common_data['close']
            comparison_data[f"{exchange}_volume"] = common_data['volume']
            comparison_data[f"{exchange}_high"] = common_data['high']
            comparison_data[f"{exchange}_low"] = common_data['low']
        
        comparison_df = pd.DataFrame(comparison_data)
        
        # Calculate spreads between exchanges
        exchanges_list = list(exchange_data.keys())
        spread_analysis = {}
        
        for i in range(len(exchanges_list)):
            for j in range(i + 1, len(exchanges_list)):
                ex1, ex2 = exchanges_list[i], exchanges_list[j]
                spread_col = f"spread_{ex1}_vs_{ex2}"
                spread_pct_col = f"spread_pct_{ex1}_vs_{ex2}"
                
                # Absolute spread
                comparison_df[spread_col] = comparison_df[f"{ex1}_close"] - comparison_df[f"{ex2}_close"]
                
                # Percentage spread
                comparison_df[spread_pct_col] = (comparison_df[spread_col] / comparison_df[f"{ex1}_close"]) * 100
                
                # Spread statistics
                spread_stats = {
                    'mean': comparison_df[spread_pct_col].mean(),
                    'std': comparison_df[spread_pct_col].std(),
                    'min': comparison_df[spread_pct_col].min(),
                    'max': comparison_df[spread_pct_col].max(),
                    'median': comparison_df[spread_pct_col].median(),
                    'skewness': comparison_df[spread_pct_col].skew(),
                    'kurtosis': comparison_df[spread_pct_col].kurtosis()
                }
                
                spread_analysis[f"{ex1}_vs_{ex2}"] = spread_stats
                
                print(f"   📊 {ex1} vs {ex2}: {spread_stats['mean']:.4f}% ± {spread_stats['std']:.4f}%")
        
        # Record analysis step
        self.analysis_steps.append({
            'step': 3,
            'title': 'Cross-Exchange Spread Analysis',
            'description': f'Calculated spreads for {coin} across {len(exchanges_list)} exchanges',
            'spread_analysis': spread_analysis,
            'common_periods': len(common_times)
        })
        
        print(f"✅ Spread analysis complete for {coin}")
        return comparison_df
    
    def identify_arbitrage_opportunities(self, coin: str, min_spread_pct: float = 0.1) -> Dict:
        """Step 4: Identify and analyze arbitrage opportunities for a specific coin"""
        print(f"\n🎯 Step 4: Arbitrage Opportunity Identification for {coin} (min spread: {min_spread_pct}%)...")
        
        comparison_df = self.calculate_cross_exchange_spreads(coin)
        if comparison_df.empty:
            return {}
        
        opportunities = {
            'coin': coin,
            'total_observations': len(comparison_df),
            'opportunities': [],
            'summary': {},
            'risk_analysis': {},
            'timing_analysis': {}
        }
        
        # Find spread columns
        spread_cols = [col for col in comparison_df.columns if col.startswith('spread_pct_')]
        
        for spread_col in spread_cols:
            # Extract exchange names
            ex1, ex2 = spread_col.replace('spread_pct_', '').split('_vs_')
            
            # Find opportunities above threshold
            above_threshold = comparison_df[comparison_df[spread_col] > min_spread_pct]
            
            if len(above_threshold) > 0:
                # Calculate opportunity metrics
                opportunity = {
                    'exchange_pair': f"{ex1}_vs_{ex2}",
                    'buy_exchange': ex1 if above_threshold[spread_col].mean() > 0 else ex2,
                    'sell_exchange': ex2 if above_threshold[spread_col].mean() > 0 else ex1,
                    'opportunity_count': len(above_threshold),
                    'opportunity_percentage': len(above_threshold) / len(comparison_df) * 100,
                    'max_spread': above_threshold[spread_col].max(),
                    'avg_spread': above_threshold[spread_col].mean(),
                    'min_spread': above_threshold[spread_col].min(),
                    'spread_volatility': above_threshold[spread_col].std(),
                    'total_volume': above_threshold[f"{ex1}_volume"].sum() + above_threshold[f"{ex2}_volume"].sum(),
                    'avg_volume': above_threshold[f"{ex1}_volume"].mean() + above_threshold[f"{ex2}_volume"].mean()
                }
                
                # Risk analysis
                opportunity['risk_score'] = self.calculate_risk_score(opportunity)
                opportunity['profitability_score'] = self.calculate_profitability_score(opportunity)
                
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
                'exchange_pairs_with_opportunities': len(opportunities['opportunities']),
                'overall_opportunity_rate': total_opps / opportunities['total_observations'] * 100
            }
            
            # Risk analysis summary
            opportunities['risk_analysis'] = self.analyze_overall_risk(opportunities['opportunities'])
            
            # Timing analysis
            opportunities['timing_analysis'] = self.analyze_opportunity_timing(comparison_df, spread_cols)
        
        print(f"✅ Found {len(opportunities['opportunities'])} exchange pairs with arbitrage opportunities")
        
        # Record analysis step
        self.analysis_steps.append({
            'step': 4,
            'title': 'Arbitrage Opportunity Identification',
            'description': f'Identified {len(opportunities["opportunities"])} exchange pairs with opportunities for {coin}',
            'opportunities_count': len(opportunities['opportunities']),
            'total_opportunities': opportunities.get('summary', {}).get('total_opportunities', 0)
        })
        
        return opportunities
    
    def calculate_risk_score(self, opportunity: Dict) -> float:
        """Calculate risk score (0-100, higher = more risky)"""
        risk_score = 0
        
        # Spread volatility risk (higher volatility = higher risk)
        if opportunity['spread_volatility'] > 1.0:  # > 1% volatility
            risk_score += 30
        elif opportunity['spread_volatility'] > 0.5:  # > 0.5% volatility
            risk_score += 20
        
        # Volume risk (lower volume = higher risk)
        if opportunity['avg_volume'] < 1000:  # Low volume
            risk_score += 25
        elif opportunity['avg_volume'] < 10000:  # Medium volume
            risk_score += 15
        
        # Opportunity frequency risk (lower frequency = higher risk)
        if opportunity['opportunity_percentage'] < 1:  # < 1% of time
            risk_score += 25
        elif opportunity['opportunity_percentage'] < 5:  # < 5% of time
            risk_score += 15
        
        return min(100, risk_score)
    
    def calculate_profitability_score(self, opportunity: Dict) -> float:
        """Calculate profitability score (0-100, higher = more profitable)"""
        profit_score = 0
        
        # Spread size (higher spread = higher profit potential)
        if opportunity['avg_spread'] > 2.0:  # > 2% spread
            profit_score += 40
        elif opportunity['avg_spread'] > 1.0:  # > 1% spread
            profit_score += 30
        elif opportunity['avg_spread'] > 0.5:  # > 0.5% spread
            profit_score += 20
        
        # Volume (higher volume = higher profit potential)
        if opportunity['avg_volume'] > 100000:  # High volume
            profit_score += 30
        elif opportunity['avg_volume'] > 10000:  # Medium volume
            profit_score += 20
        
        # Opportunity frequency (higher frequency = higher profit potential)
        if opportunity['opportunity_percentage'] > 10:  # > 10% of time
            profit_score += 30
        elif opportunity['opportunity_percentage'] > 5:  # > 5% of time
            profit_score += 20
        
        return min(100, profit_score)
    
    def analyze_overall_risk(self, opportunities: List) -> Dict:
        """Analyze overall risk profile of opportunities"""
        if not opportunities:
            return {}
        
        risk_scores = [opp['risk_score'] for opp in opportunities]
        profit_scores = [opp['profitability_score'] for opp in opportunities]
        
        return {
            'avg_risk_score': np.mean(risk_scores),
            'avg_profitability_score': np.mean(profit_scores),
            'risk_distribution': {
                'low_risk': len([r for r in risk_scores if r < 30]),
                'medium_risk': len([r for r in risk_scores if 30 <= r < 60]),
                'high_risk': len([r for r in risk_scores if r >= 60])
            },
            'profitability_distribution': {
                'low_profit': len([p for p in profit_scores if p < 30]),
                'medium_profit': len([p for p in profit_scores if 30 <= p < 60]),
                'high_profit': len([p for p in profit_scores if p >= 60])
            }
        }
    
    def analyze_opportunity_timing(self, comparison_df: pd.DataFrame, spread_cols: List) -> Dict:
        """Analyze timing patterns of arbitrage opportunities"""
        timing_analysis = {}
        
        for spread_col in spread_cols:
            # Extract exchange names
            ex1, ex2 = spread_col.replace('spread_pct_', '').split('_vs_')
            
            # Calculate hourly patterns
            comparison_df['hour'] = comparison_df.index.hour
            hourly_spreads = comparison_df.groupby('hour')[spread_col].agg(['mean', 'std', 'count'])
            
            # Find best hours for arbitrage
            best_hours = hourly_spreads.nlargest(3, 'mean')
            worst_hours = hourly_spreads.nsmallest(3, 'mean')
            
            timing_analysis[f"{ex1}_vs_{ex2}"] = {
                'best_hours': best_hours.index.tolist(),
                'worst_hours': worst_hours.index.tolist(),
                'hourly_pattern': hourly_spreads.to_dict()
            }
        
        return timing_analysis
    
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
        self.create_enhanced_visualizations(all_opportunities)
        
        # Step 7: Generate Comprehensive Report
        print("\n📋 Step 7: Generating Comprehensive Analysis Report...")
        report = self.generate_enhanced_report(all_opportunities)
        
        # Step 8: Save All Analysis Results
        print("\n💾 Step 8: Saving Analysis Results...")
        self.save_analysis_results(all_opportunities)
        
        print("\n🎉 Enhanced Analysis Pipeline Complete!")
        print("=" * 80)
        
        return all_opportunities
    
    def create_enhanced_visualizations(self, opportunities: Dict):
        """Create comprehensive enhanced visualizations"""
        print("   📊 Creating enhanced visualizations...")
        
        # Create multiple visualization types
        self.create_opportunity_summary_charts(opportunities)
        self.create_risk_profitability_analysis(opportunities)
        self.create_timing_analysis_charts(opportunities)
        self.create_data_quality_charts(opportunities)
        
        print("   ✅ Enhanced visualizations complete")
    
    def create_opportunity_summary_charts(self, opportunities: Dict):
        """Create opportunity summary charts"""
        coins_with_opps = [coin for coin, data in opportunities.items() 
                          if isinstance(data, dict) and data.get('opportunities')]
        
        if not coins_with_opps:
            return
        
        # Create subplots
        fig, axes = plt.subplots(2, 2, figsize=(20, 15))
        fig.suptitle('Enhanced Arbitrage Opportunity Analysis', fontsize=16, fontweight='bold')
        
        # Opportunities per coin
        opp_counts = [opportunities[coin]['summary']['total_opportunities'] for coin in coins_with_opps]
        axes[0,0].bar(coins_with_opps, opp_counts, color='skyblue', alpha=0.7)
        axes[0,0].set_title('Total Arbitrage Opportunities per Coin')
        axes[0,0].set_ylabel('Number of Opportunities')
        axes[0,0].tick_params(axis='x', rotation=45)
        
        # Average spreads per coin
        avg_spreads = [opportunities[coin]['summary']['average_spread'] for coin in coins_with_opps]
        axes[0,1].bar(coins_with_opps, avg_spreads, color='lightgreen', alpha=0.7)
        axes[0,1].set_title('Average Spread per Coin')
        axes[0,1].set_ylabel('Spread (%)')
        axes[0,1].tick_params(axis='x', rotation=45)
        
        # Opportunity rates per coin
        opp_rates = [opportunities[coin]['summary']['overall_opportunity_rate'] for coin in coins_with_opps]
        axes[1,0].bar(coins_with_opps, opp_rates, color='gold', alpha=0.7)
        axes[1,0].set_title('Opportunity Rate per Coin')
        axes[1,0].set_ylabel('Opportunity Rate (%)')
        axes[1,0].tick_params(axis='x', rotation=45)
        
        # Risk vs Profitability scatter
        risk_scores = []
        profit_scores = []
        for coin in coins_with_opps:
            for opp in opportunities[coin]['opportunities']:
                risk_scores.append(opp['risk_score'])
                profit_scores.append(opp['profitability_score'])
        
        if risk_scores and profit_scores:
            axes[1,1].scatter(risk_scores, profit_scores, alpha=0.6, color='red')
            axes[1,1].set_xlabel('Risk Score')
            axes[1,1].set_ylabel('Profitability Score')
            axes[1,1].set_title('Risk vs Profitability Analysis')
            axes[1,1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save visualization
        viz_file = self.data_folder / "analysis" / "enhanced_arbitrage_analysis.png"
        plt.savefig(viz_file, dpi=300, bbox_inches='tight')
        print(f"   💾 Saved opportunity summary charts to {viz_file}")
        
        plt.show()
    
    def create_risk_profitability_analysis(self, opportunities: Dict):
        """Create risk vs profitability analysis charts"""
        # Implementation for risk-profitability analysis
        pass
    
    def create_timing_analysis_charts(self, opportunities: Dict):
        """Create timing analysis charts"""
        # Implementation for timing analysis
        pass
    
    def create_data_quality_charts(self, opportunities: Dict):
        """Create data quality analysis charts"""
        # Implementation for data quality charts
        pass
    
    def generate_enhanced_report(self, opportunities: Dict) -> str:
        """Generate comprehensive enhanced analysis report"""
        print("   📋 Generating enhanced analysis report...")
        
        report = []
        report.append("# Enhanced Cross-Exchange Arbitrage Opportunity Analysis Report")
        report.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Data Source:** {self.data_folder}")
        report.append(f"**Exchanges Analyzed:** {', '.join(self.exchanges)}")
        report.append(f"**Coins Analyzed:** {', '.join(self.coins)}")
        report.append("")
        
        # Analysis Methodology
        report.append("## Analysis Methodology")
        report.append("This enhanced analysis follows a comprehensive 8-step methodology:")
        for step in self.analysis_steps:
            report.append(f"{step['step']}. **{step['title']}**: {step['description']}")
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
        
        # Data Quality Summary
        report.append("## Data Quality Assessment")
        if 'quality_reports' in opportunities.get('overall_summary', {}):
            quality_reports = opportunities['overall_summary']['quality_reports']
            for coin, report_data in quality_reports.items():
                if report_data and report_data.get('overall_quality'):
                    quality = report_data['overall_quality']
                    report.append(f"### {coin}")
                    report.append(f"- **Data Completeness:** {quality['data_completeness']:.1f}%")
                    report.append(f"- **Exchange Coverage:** {quality['exchange_coverage']}")
                    report.append(f"- **Total Records:** {quality['total_records']:,}")
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
                    report.append(f"- **Overall Opportunity Rate:** {data['summary']['overall_opportunity_rate']:.2f}%")
                
                # Risk and profitability analysis
                if data.get('risk_analysis'):
                    risk = data['risk_analysis']
                    report.append(f"- **Risk Profile:**")
                    report.append(f"  - Low Risk: {risk['risk_distribution']['low_risk']}")
                    report.append(f"  - Medium Risk: {risk['risk_distribution']['medium_risk']}")
                    report.append(f"  - High Risk: {risk['risk_distribution']['high_risk']}")
                
                report.append("")
                
                # Exchange pair details
                for opp in data['opportunities']:
                    report.append(f"#### {opp['exchange_pair']}")
                    report.append(f"- **Buy Exchange:** {opp['buy_exchange']}")
                    report.append(f"- **Sell Exchange:** {opp['sell_exchange']}")
                    report.append(f"- **Opportunities:** {opp['opportunity_count']:,} ({opp['opportunity_percentage']:.2f}%)")
                    report.append(f"- **Spread Range:** {opp['min_spread']:.4f}% - {opp['max_spread']:.4f}%")
                    report.append(f"- **Average Spread:** {opp['avg_spread']:.4f}%")
                    report.append(f"- **Risk Score:** {opp['risk_score']:.1f}/100")
                    report.append(f"- **Profitability Score:** {opp['profitability_score']:.1f}/100")
                    report.append(f"- **Total Volume:** {opp['total_volume']:,.2f}")
                    report.append("")
            else:
                report.append(f"### {coin}")
                report.append("- **No arbitrage opportunities found**")
                report.append("")
        
        # Strategic recommendations
        report.append("## Strategic Recommendations")
        report.append("")
        report.append("### High-Priority Opportunities")
        
        # Find top opportunities based on composite score
        all_opps = []
        for coin, data in opportunities.items():
            if isinstance(data, dict) and data.get('opportunities'):
                for opp in data['opportunities']:
                    opp['coin'] = coin
                    # Calculate composite score (profitability - risk)
                    composite_score = opp['profitability_score'] - opp['risk_score']
                    opp['composite_score'] = composite_score
                    all_opps.append(opp)
        
        if all_opps:
            # Sort by composite score
            all_opps.sort(key=lambda x: x['composite_score'], reverse=True)
            
            for i, opp in enumerate(all_opps[:5]):
                report.append(f"{i+1}. **{opp['coin']} - {opp['exchange_pair']}**")
                report.append(f"   - Composite Score: {opp['composite_score']:.1f}")
                report.append(f"   - Profitability: {opp['profitability_score']:.1f}/100")
                report.append(f"   - Risk: {opp['risk_score']:.1f}/100")
                report.append(f"   - Opportunity Rate: {opp['opportunity_percentage']:.2f}%")
                report.append(f"   - Average Spread: {opp['avg_spread']:.4f}%")
                report.append("")
        
        report.append("### Implementation Strategy")
        report.append("1. **Start with high-composite-score pairs** - Focus on profitable, low-risk opportunities")
        report.append("2. **Exchange prioritization** - Begin with most liquid exchange pairs")
        report.append("3. **Risk management** - Implement strict risk score thresholds")
        report.append("4. **Execution optimization** - Develop fast execution algorithms for identified opportunities")
        report.append("5. **Continuous monitoring** - Set up real-time opportunity detection with risk scoring")
        report.append("6. **Data quality maintenance** - Regular data quality assessments")
        
        # Save report
        report_text = "\n".join(report)
        report_file = self.data_folder / "analysis" / "enhanced_arbitrage_analysis_report.md"
        
        with open(report_file, 'w') as f:
            f.write(report_text)
        
        print(f"   💾 Saved enhanced report to {report_file}")
        return report_text
    
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
    
    args = parser.parse_args()
    
    # Initialize enhanced analyzer
    analyzer = EnhancedCrossExchangeArbitrageAnalyzer(args.data_folder)
    
    if args.coin:
        # Analyze specific coin
        print(f"🎯 Running enhanced analysis for {args.coin}...")
        opportunities = analyzer.identify_arbitrage_opportunities(args.coin, args.min_spread)
        print(f"\n📊 Enhanced analysis results for {args.coin}:")
        print(json.dumps(opportunities, indent=2, default=str))
    else:
        # Run complete enhanced analysis
        analyzer.run_complete_enhanced_analysis(args.min_spread)

if __name__ == "__main__":
    main()
