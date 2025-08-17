#!/usr/bin/env python3
"""
Etherscan Data Collection Script for DEX Arbitrage Backtesting

This script fetches historical blockchain data from Etherscan and stores it
in the database for later analysis.
"""

import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from fetcher.etherscan_fetcher import EtherscanFetcher
from database.schema import create_database, EventSwap, EventSync, Pair, Exchange
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import logging
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_database_engine():
    """Get database engine"""
    from database.schema import get_database_url
    db_url = get_database_url()
    return create_engine(db_url, echo=False)

def fetch_and_store_swap_events(fetcher, session, router_address, exchange_name, 
                               from_block, to_block, batch_size=1000):
    """Fetch swap events and store them in the database"""
    
    console.print(f"[bold blue]Fetching swap events from {exchange_name} router...[/bold blue]")
    
    # Get all pairs for this exchange
    exchange = session.query(Exchange).filter(Exchange.name == exchange_name).first()
    if not exchange:
        console.print(f"[red]Exchange {exchange_name} not found in database[/red]")
        return 0
    
    pairs = session.query(Pair).filter(Pair.exchange_id == exchange.exchange_id).all()
    pair_addresses = {pair.pair_address for pair in pairs}
    
    if not pair_addresses:
        console.print(f"[yellow]No pairs found for {exchange_name}[/yellow]")
        return 0
    
    console.print(f"Found {len(pair_addresses)} pairs for {exchange_name}")
    
    total_events = 0
    stored_events = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        
        task = progress.add_task(
            f"Fetching swap events from {from_block} to {to_block}",
            total=to_block - from_block
        )
        
        try:
            for event in fetcher.get_swap_events(
                router_address=router_address,
                from_block=from_block,
                to_block=to_block,
                batch_size=batch_size
            ):
                total_events += 1
                
                # Only store events for pairs we're tracking
                if event['pair_address'] in pair_addresses:
                    # Check if event already exists
                    existing = session.query(EventSwap).filter(
                        EventSwap.tx_hash == event['tx_hash'],
                        EventSwap.log_index == event['log_index']
                    ).first()
                    
                    if not existing:
                        swap_event = EventSwap(**event)
                        session.add(swap_event)
                        stored_events += 1
                        
                        # Commit every 100 events to avoid memory issues
                        if stored_events % 100 == 0:
                            session.commit()
                            console.print(f"[green]Stored {stored_events} events so far...[/green]")
                
                # Update progress
                if total_events % 100 == 0:
                    progress.update(task, completed=total_events)
            
            # Final commit
            session.commit()
            
        except Exception as e:
            console.print(f"[red]Error during event fetching: {e}[/red]")
            session.rollback()
            raise
    
    console.print(f"[green]✅ Stored {stored_events} swap events from {total_events} total[/green]")
    return stored_events

def fetch_and_store_sync_events(fetcher, session, from_block, to_block, batch_size=1000):
    """Fetch sync events for all tracked pairs"""
    
    console.print(f"[bold blue]Fetching sync events for all pairs...[/bold blue]")
    
    # Get all pairs
    pairs = session.query(Pair).all()
    console.print(f"Found {len(pairs)} pairs to track")
    
    total_events = 0
    stored_events = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        
        task = progress.add_task(
            f"Fetching sync events for {len(pairs)} pairs",
            total=len(pairs)
        )
        
        for i, pair in enumerate(pairs):
            try:
                pair_events = 0
                
                for event in fetcher.get_sync_events(
                    pair_address=pair.pair_address,
                    from_block=from_block,
                    to_block=to_block,
                    batch_size=batch_size
                ):
                    # Check if event already exists
                    existing = session.query(EventSync).filter(
                        EventSync.pair_address == event['pair_address'],
                        EventSync.block_number == event['block_number'],
                        EventSync.log_index == event['log_index']
                    ).first()
                    
                    if not existing:
                        sync_event = EventSync(**event)
                        session.add(sync_event)
                        pair_events += 1
                        stored_events += 1
                
                # Commit after each pair to avoid memory issues
                session.commit()
                
                if pair_events > 0:
                    console.print(f"[green]Stored {pair_events} sync events for {pair.pair_address[:10]}...[/green]")
                
                progress.update(task, completed=i + 1)
                
            except Exception as e:
                console.print(f"[red]Error fetching sync events for pair {pair.pair_address}: {e}[/red]")
                session.rollback()
                continue
    
    console.print(f"[green]✅ Stored {stored_events} sync events total[/green]")
    return stored_events

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Fetch Etherscan data for DEX arbitrage backtesting")
    parser.add_argument('--start-block', type=int, required=True, help='Starting block number')
    parser.add_argument('--end-block', type=int, required=True, help='Ending block number')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for API calls')
    parser.add_argument('--exchanges', nargs='+', default=['Uniswap V2', 'SushiSwap'], 
                       help='Exchanges to fetch data for')
    parser.add_argument('--skip-sync', action='store_true', help='Skip fetching sync events')
    parser.add_argument('--setup-db', action='store_true', help='Setup database if it doesn\'t exist')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    console.print("[bold green]🚀 DEX Arbitrage Backtesting - Data Collection[/bold green]")
    console.print(f"📊 Block range: {args.start_block:,} to {args.end_block:,}")
    console.print(f"🏪 Exchanges: {', '.join(args.exchanges)}")
    console.print(f"⚙️ Batch size: {args.batch_size:,}")
    
    # Initialize database
    if args.setup_db:
        console.print("[bold blue]Setting up database...[/bold blue]")
        from database.schema import create_database
        engine = create_database()
    else:
        engine = get_database_engine()
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Initialize fetcher
    fetcher = EtherscanFetcher()
    
    try:
        # Exchange router addresses
        routers = {
            'Uniswap V2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            'SushiSwap': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
        }
        
        total_swap_events = 0
        total_sync_events = 0
        
        # Fetch swap events for each exchange
        for exchange_name in args.exchanges:
            if exchange_name in routers:
                router_address = routers[exchange_name]
                events_count = fetch_and_store_swap_events(
                    fetcher=fetcher,
                    session=session,
                    router_address=router_address,
                    exchange_name=exchange_name,
                    from_block=args.start_block,
                    to_block=args.end_block,
                    batch_size=args.batch_size
                )
                total_swap_events += events_count
            else:
                console.print(f"[yellow]⚠️ No router address found for {exchange_name}[/yellow]")
        
        # Fetch sync events (reserve updates)
        if not args.skip_sync:
            total_sync_events = fetch_and_store_sync_events(
                fetcher=fetcher,
                session=session,
                from_block=args.start_block,
                to_block=args.end_block,
                batch_size=args.batch_size
            )
        
        # Summary
        console.print("\n[bold green]📋 Collection Summary[/bold green]")
        console.print(f"🔄 Swap Events: {total_swap_events:,}")
        console.print(f"📊 Sync Events: {total_sync_events:,}")
        console.print(f"📈 Total Events: {total_swap_events + total_sync_events:,}")
        
        # Show database stats
        console.print("\n[bold blue]📊 Database Statistics[/bold blue]")
        
        swap_count = session.query(EventSwap).count()
        sync_count = session.query(EventSync).count()
        pair_count = session.query(Pair).count()
        
        table = Table(title="Database Contents")
        table.add_column("Table", style="cyan")
        table.add_column("Record Count", style="magenta")
        
        table.add_row("Swap Events", f"{swap_count:,}")
        table.add_row("Sync Events", f"{sync_count:,}")
        table.add_row("Trading Pairs", f"{pair_count:,}")
        
        console.print(table)
        
        console.print("\n[bold green]✅ Data collection completed successfully![/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Data collection interrupted by user[/yellow]")
        session.rollback()
    except Exception as e:
        console.print(f"\n[red]❌ Error during data collection: {e}[/red]")
        session.rollback()
        raise
    finally:
        fetcher.close()
        session.close()

if __name__ == "__main__":
    main()
