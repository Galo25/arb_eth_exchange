#!/usr/bin/env python3
"""
Main Arbitrage Analysis Script for DEX Arbitrage Backtesting System

This script orchestrates the complete analysis pipeline:
1. Data Collection (if needed)
2. Event Parsing and Pool State Reconstruction
3. Arbitrage Opportunity Detection
4. Trade Simulation and Analysis
5. Results Generation and Reporting
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from fetcher.etherscan_fetcher import EtherscanFetcher
from parser.event_parser import EventParser
from analyzer.arbitrage_analyzer import ArbitrageAnalyzer
from database.schema import create_database, get_database_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
import logging
from loguru import logger

console = Console()

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def check_database_status(engine) -> dict:
    """Check the current status of the database"""
    try:
        with engine.connect() as conn:
            # Check table counts
            tables = ['events_swaps', 'events_syncs', 'pairs', 'tokens', 'exchanges']
            counts = {}
            
            for table in tables:
                result = conn.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = result.fetchone()[0]
            
            return counts
            
    except Exception as e:
        logger.error(f"Error checking database status: {e}")
        return {}

def collect_data_if_needed(fetcher, session, start_block: int, end_block: int, 
                          exchanges: list, force_collect: bool = False) -> bool:
    """Collect data if it doesn't exist or if forced"""
    try:
        # Check if we have data for this block range
        if not force_collect:
            with session.begin():
                result = session.execute(
                    "SELECT COUNT(*) FROM events_syncs WHERE block_number BETWEEN :start AND :end",
                    {"start": start_block, "end": end_block}
                )
                existing_count = result.fetchone()[0]
                
                if existing_count > 0:
                    console.print(f"[green]✅ Found {existing_count:,} existing events in block range[/green]")
                    return True
        
        console.print("[bold blue]📥 Collecting new data...[/bold blue]")
        
        # Exchange router addresses
        routers = {
            'Uniswap V2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            'SushiSwap': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
        }
        
        total_events = 0
        
        for exchange_name in exchanges:
            if exchange_name in routers:
                router_address = routers[exchange_name]
                console.print(f"[blue]Fetching data for {exchange_name}...[/blue]")
                
                # Fetch swap events
                events = list(fetcher.get_swap_events(
                    router_address=router_address,
                    from_block=start_block,
                    to_block=end_block,
                    batch_size=1000
                ))
                
                # Store events (simplified - you'd want proper storage here)
                console.print(f"[green]Found {len(events):,} events for {exchange_name}[/green]")
                total_events += len(events)
        
        console.print(f"[green]✅ Data collection complete! Total events: {total_events:,}[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Error during data collection: {e}[/red]")
        return False

def run_arbitrage_analysis(start_block: int, end_block: int, 
                          min_spread_bps: int = 50, 
                          exchanges: list = None,
                          force_collect: bool = False) -> dict:
    """Run the complete arbitrage analysis pipeline"""
    
    if exchanges is None:
        exchanges = ['Uniswap V2', 'SushiSwap']
    
    console.print(f"[bold green]🚀 Starting DEX Arbitrage Analysis[/bold green]")
    console.print(f"📊 Block range: {start_block:,} to {end_block:,}")
    console.print(f"🏪 Exchanges: {', '.join(exchanges)}")
    console.print(f"💰 Minimum spread: {min_spread_bps} bps ({min_spread_bps/100:.2f}%)")
    
    # Initialize components
    fetcher = EtherscanFetcher()
    parser = EventParser()
    analyzer = ArbitrageAnalyzer(min_spread_bps=min_spread_bps)
    
    try:
        # Check database status
        engine = create_engine(get_database_url(), echo=False)
        db_status = check_database_status(engine)
        
        console.print("\n[bold blue]📊 Database Status:[/bold blue]")
        for table, count in db_status.items():
            console.print(f"  {table}: {count:,} records")
        
        # Collect data if needed
        Session = sessionmaker(bind=engine)
        session = Session()
        
        data_ready = collect_data_if_needed(
            fetcher, session, start_block, end_block, exchanges, force_collect
        )
        
        if not data_ready:
            console.print("[red]❌ Data collection failed. Cannot proceed with analysis.[/red]")
            return {}
        
        # Run arbitrage analysis
        console.print("\n[bold blue]🔍 Running Arbitrage Analysis...[/bold blue]")
        
        df_opportunities, df_trades = analyzer.analyze_historical_opportunities(
            start_block, end_block, min_spread_bps
        )
        
        if len(df_opportunities) == 0:
            console.print("[yellow]⚠️ No arbitrage opportunities found in this block range[/yellow]")
            return {}
        
        # Generate summary
        summary = analyzer.get_opportunity_summary(df_opportunities, df_trades)
        
        # Display results
        console.print("\n[bold green]📋 Analysis Results[/bold green]")
        console.print("=" * 50)
        
        # Opportunities summary
        opp_table = Table(title="Arbitrage Opportunities Summary")
        opp_table.add_column("Metric", style="cyan")
        opp_table.add_column("Value", style="magenta")
        
        opp_table.add_row("Total Opportunities", f"{summary['total_opportunities']:,}")
        opp_table.add_row("Average Spread", f"{summary['avg_spread_bps']:.2f} bps")
        opp_table.add_row("Maximum Spread", f"{summary['max_spread_bps']:.2f} bps")
        
        console.print(opp_table)
        
        # Trades summary
        trades_table = Table(title="Trade Simulation Results")
        trades_table.add_column("Metric", style="cyan")
        trades_table.add_column("Value", style="magenta")
        
        trades_table.add_row("Total Trades Simulated", f"{summary['total_trades']:,}")
        trades_table.add_row("Profitable Trades", f"{summary['profitable_trades']:,}")
        trades_table.add_row("Profitability Rate", f"{summary['profitable_rate']*100:.1f}%")
        trades_table.add_row("Total Gross Profit", f"${summary['total_gross_profit']:,.2f}")
        trades_table.add_row("Total Net Profit", f"${summary['total_net_profit']:,.2f}")
        trades_table.add_row("Total Gas Costs", f"${summary['total_gas_costs']:,.2f}")
        trades_table.add_row("Average ROI", f"{summary['avg_roi']:.2f}%")
        
        console.print(trades_table)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save opportunities
        opp_filename = f"arbitrage_opportunities_{start_block}_{end_block}_{timestamp}.csv"
        df_opportunities.to_csv(opp_filename, index=False)
        console.print(f"[green]✅ Opportunities saved to: {opp_filename}[/green]")
        
        # Save trades
        trades_filename = f"arbitrage_trades_{start_block}_{end_block}_{timestamp}.csv"
        df_trades.to_csv(trades_filename, index=False)
        console.print(f"[green]✅ Trades saved to: {trades_filename}[/green]")
        
        # Save summary
        summary_filename = f"analysis_summary_{start_block}_{end_block}_{timestamp}.txt"
        with open(summary_filename, 'w') as f:
            f.write("DEX Arbitrage Analysis Summary\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Block Range: {start_block:,} to {end_block:,}\n")
            f.write(f"Exchanges: {', '.join(exchanges)}\n")
            f.write(f"Minimum Spread: {min_spread_bps} bps\n\n")
            
            f.write("OPPORTUNITIES SUMMARY:\n")
            f.write("-" * 20 + "\n")
            for key, value in summary.items():
                if 'opportunities' in key or 'spread' in key:
                    if isinstance(value, float):
                        f.write(f"{key}: {value:.2f}\n")
                    else:
                        f.write(f"{key}: {value:,}\n")
            
            f.write("\nTRADES SUMMARY:\n")
            f.write("-" * 20 + "\n")
            for key, value in summary.items():
                if 'trades' in key or 'profit' in key or 'roi' in key:
                    if isinstance(value, float):
                        f.write(f"{key}: {value:.2f}\n")
                    else:
                        f.write(f"{key}: {value:,}\n")
        
        console.print(f"[green]✅ Summary saved to: {summary_filename}[/green]")
        
        return {
            'opportunities': df_opportunities,
            'trades': df_trades,
            'summary': summary,
            'files': {
                'opportunities': opp_filename,
                'trades': trades_filename,
                'summary': summary_filename
            }
        }
        
    except Exception as e:
        console.print(f"[red]❌ Error during analysis: {e}[/red]")
        logger.error(f"Analysis failed: {e}")
        return {}
    finally:
        fetcher.close()
        parser.close()
        analyzer.close()
        session.close()

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Run DEX arbitrage analysis")
    parser.add_argument('--start-block', type=int, required=True, help='Starting block number')
    parser.add_argument('--end-block', type=int, required=True, help='Ending block number')
    parser.add_argument('--min-spread', type=int, default=50, help='Minimum spread in basis points (default: 50)')
    parser.add_argument('--exchanges', nargs='+', default=['Uniswap V2', 'SushiSwap'], 
                       help='Exchanges to analyze')
    parser.add_argument('--force-collect', action='store_true', help='Force data collection even if data exists')
    parser.add_argument('--setup-db', action='store_true', help='Setup database if it doesn\'t exist')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    # Setup database if requested
    if args.setup_db:
        console.print("[bold blue]Setting up database...[/bold blue]")
        try:
            from database.schema import create_database
            create_database()
            console.print("[green]✅ Database setup complete[/green]")
        except Exception as e:
            console.print(f"[red]❌ Database setup failed: {e}[/red]")
            return
    
    # Validate arguments
    if args.start_block >= args.end_block:
        console.print("[red]❌ Start block must be less than end block[/red]")
        return
    
    if args.min_spread < 1:
        console.print("[red]❌ Minimum spread must be at least 1 basis point[/red]")
        return
    
    # Run analysis
    results = run_arbitrage_analysis(
        start_block=args.start_block,
        end_block=args.end_block,
        min_spread_bps=args.min_spread,
        exchanges=args.exchanges,
        force_collect=args.force_collect
    )
    
    if results:
        console.print("\n[bold green]🎉 Analysis completed successfully![/bold green]")
        console.print("\n[bold blue]📁 Generated Files:[/bold blue]")
        for file_type, filename in results['files'].items():
            console.print(f"  {file_type.title()}: {filename}")
    else:
        console.print("\n[red]❌ Analysis failed or no results generated[/red]")

if __name__ == "__main__":
    main()
