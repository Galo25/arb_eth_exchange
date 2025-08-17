"""
Event Parser for DEX Arbitrage Backtesting System

This module handles parsing and normalizing blockchain events to reconstruct
pool states and calculate prices for arbitrage analysis.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

class EventParser:
    """Parses and normalizes blockchain events for arbitrage analysis"""
    
    def __init__(self, database_url: str = None):
        """Initialize the event parser"""
        self.database_url = database_url or 'sqlite:///dex_arbitrage.db'
        self.engine = create_engine(self.database_url, echo=False)
        self.Session = sessionmaker(bind=self.engine)
        
    def get_token_decimals(self, token_address: str) -> int:
        """Get token decimals from database"""
        with self.Session() as session:
            result = session.execute(
                text("SELECT decimals FROM tokens WHERE token_address = :address"),
                {"address": token_address}
            ).fetchone()
            
            if result:
                return result[0]
            else:
                logger.warning(f"Token {token_address} not found in database, using default 18 decimals")
                return 18
    
    def normalize_token_amount(self, amount: int, token_address: str) -> float:
        """Normalize raw token amount using decimals"""
        decimals = self.get_token_decimals(token_address)
        return amount / (10 ** decimals)
    
    def parse_swap_event(self, event_data: Dict) -> Dict:
        """Parse and normalize a swap event"""
        try:
            # Get token addresses for the pair
            with self.Session() as session:
                result = session.execute(
                    text("""
                        SELECT token0_address, token1_address 
                        FROM pairs 
                        WHERE pair_address = :pair_address
                    """),
                    {"pair_address": event_data['pair_address']}
                ).fetchone()
                
                if not result:
                    logger.warning(f"Pair {event_data['pair_address']} not found in database")
                    return None
                
                token0_address, token1_address = result
            
            # Normalize amounts
            normalized_event = {
                'pair_address': event_data['pair_address'],
                'block_number': event_data['block_number'],
                'timestamp': event_data['timestamp'],
                'tx_hash': event_data['tx_hash'],
                'log_index': event_data['log_index'],
                'sender': event_data['sender'],
                'to_address': event_data['to_address'],
                
                # Normalized amounts
                'amount0_in_normalized': self.normalize_token_amount(
                    event_data['amount0_in'], token0_address
                ) if event_data['amount0_in'] else 0,
                'amount1_in_normalized': self.normalize_token_amount(
                    event_data['amount1_in'], token1_address
                ) if event_data['amount1_in'] else 0,
                'amount0_out_normalized': self.normalize_token_amount(
                    event_data['amount0_out'], token0_address
                ) if event_data['amount0_out'] else 0,
                'amount1_out_normalized': self.normalize_token_amount(
                    event_data['amount1_out'], token1_address
                ) if event_data['amount1_out'] else 0,
                
                # Raw amounts (for reference)
                'amount0_in_raw': event_data['amount0_in'],
                'amount1_in_raw': event_data['amount1_in'],
                'amount0_out_raw': event_data['amount0_out'],
                'amount1_out_raw': event_data['amount1_out']
            }
            
            return normalized_event
            
        except Exception as e:
            logger.error(f"Error parsing swap event: {e}")
            return None
    
    def parse_sync_event(self, event_data: Dict) -> Dict:
        """Parse and normalize a sync event (reserve update)"""
        try:
            # Get token addresses for the pair
            with self.Session() as session:
                result = session.execute(
                    text("""
                        SELECT token0_address, token1_address 
                        FROM pairs 
                        WHERE pair_address = :pair_address
                    """),
                    {"pair_address": event_data['pair_address']}
                ).fetchone()
                
                if not result:
                    logger.warning(f"Pair {event_data['pair_address']} not found in database")
                    return None
                
                token0_address, token1_address = result
            
            # Normalize reserves
            normalized_event = {
                'pair_address': event_data['pair_address'],
                'block_number': event_data['block_number'],
                'timestamp': event_data['timestamp'],
                'tx_hash': event_data['tx_hash'],
                'log_index': event_data['log_index'],
                
                # Normalized reserves
                'reserve0_normalized': self.normalize_token_amount(
                    event_data['reserve0'], token0_address
                ),
                'reserve1_normalized': self.normalize_token_amount(
                    event_data['reserve1'], token1_address
                ),
                
                # Raw reserves (for reference)
                'reserve0_raw': event_data['reserve0'],
                'reserve1_raw': event_data['reserve1']
            }
            
            return normalized_event
            
        except Exception as e:
            logger.error(f"Error parsing sync event: {e}")
            return None
    
    def calculate_pool_price(self, reserve0: float, reserve1: float, 
                           token0_symbol: str, token1_symbol: str) -> Dict:
        """Calculate pool price from reserves"""
        try:
            if reserve0 == 0 or reserve1 == 0:
                return None
            
            # Price of token0 in terms of token1
            price_token0_in_token1 = reserve1 / reserve0
            
            # Price of token1 in terms of token0
            price_token1_in_token0 = reserve0 / reserve1
            
            return {
                'price_token0_in_token1': price_token0_in_token1,
                'price_token1_in_token0': price_token1_in_token0,
                'inverse_price': 1 / price_token0_in_token1,
                'token0_symbol': token0_symbol,
                'token1_symbol': token1_symbol
            }
            
        except Exception as e:
            logger.error(f"Error calculating pool price: {e}")
            return None
    
    def reconstruct_pool_state(self, pair_address: str, block_number: int) -> Optional[Dict]:
        """Reconstruct pool state at a specific block"""
        try:
            with self.Session() as session:
                # Get the most recent sync event up to this block
                result = session.execute(
                    text("""
                        SELECT e.*, p.token0_address, p.token1_address, 
                               t0.symbol as token0_symbol, t1.symbol as token1_symbol,
                               ex.name as exchange_name
                        FROM events_syncs e
                        JOIN pairs p ON e.pair_address = p.pair_address
                        JOIN tokens t0 ON p.token0_address = t0.token_address
                        JOIN tokens t1 ON p.token1_address = t1.token_address
                        JOIN exchanges ex ON p.exchange_id = ex.exchange_id
                        WHERE e.pair_address = :pair_address 
                        AND e.block_number <= :block_number
                        ORDER BY e.block_number DESC
                        LIMIT 1
                    """),
                    {
                        "pair_address": pair_address,
                        "block_number": block_number
                    }
                ).fetchone()
                
                if not result:
                    return None
                
                # Parse the sync event
                sync_data = dict(result)
                normalized_sync = self.parse_sync_event(sync_data)
                
                if not normalized_sync:
                    return None
                
                # Calculate prices
                prices = self.calculate_pool_price(
                    normalized_sync['reserve0_normalized'],
                    normalized_sync['reserve1_normalized'],
                    sync_data['token0_symbol'],
                    sync_data['token1_symbol']
                )
                
                if not prices:
                    return None
                
                # Construct pool state
                pool_state = {
                    'pair_address': pair_address,
                    'block_number': block_number,
                    'timestamp': sync_data['timestamp'],
                    'exchange_name': sync_data['exchange_name'],
                    'token0_symbol': sync_data['token0_symbol'],
                    'token1_symbol': sync_data['token1_symbol'],
                    'reserve0': normalized_sync['reserve0_normalized'],
                    'reserve1': normalized_sync['reserve1_normalized'],
                    'price_token0_in_token1': prices['price_token0_in_token1'],
                    'price_token1_in_token0': prices['price_token1_in_token0'],
                    'liquidity_usd': self.estimate_liquidity_usd(
                        normalized_sync['reserve0_normalized'],
                        normalized_sync['reserve1_normalized'],
                        prices['price_token0_in_token1']
                    )
                }
                
                return pool_state
                
        except Exception as e:
            logger.error(f"Error reconstructing pool state: {e}")
            return None
    
    def estimate_liquidity_usd(self, reserve0: float, reserve1: float, 
                              price_token0_in_token1: float) -> float:
        """Estimate total liquidity in USD (simplified)"""
        try:
            # This is a simplified calculation - in production you'd use real price feeds
            # Assuming token1 is a stablecoin (USDC/USDT) for now
            liquidity_usd = reserve1 * 2  # Total value in stablecoin terms
            return liquidity_usd
        except:
            return 0.0
    
    def get_pool_states_for_blocks(self, pair_address: str, 
                                  from_block: int, to_block: int) -> List[Dict]:
        """Get pool states for a range of blocks"""
        pool_states = []
        
        try:
            with self.Session() as session:
                # Get all sync events in the block range
                result = session.execute(
                    text("""
                        SELECT DISTINCT block_number 
                        FROM events_syncs 
                        WHERE pair_address = :pair_address 
                        AND block_number BETWEEN :from_block AND :to_block
                        ORDER BY block_number
                    """),
                    {
                        "pair_address": pair_address,
                        "from_block": from_block,
                        "to_block": to_block
                    }
                ).fetchall()
                
                for row in result:
                    block_number = row[0]
                    pool_state = self.reconstruct_pool_state(pair_address, block_number)
                    if pool_state:
                        pool_states.append(pool_state)
                
        except Exception as e:
            logger.error(f"Error getting pool states: {e}")
        
        return pool_states
    
    def calculate_price_impact(self, amount_in: float, reserve_in: float, 
                              reserve_out: float) -> Dict:
        """Calculate price impact using constant product AMM formula"""
        try:
            # Constant product formula: (x + dx) * (y - dy) = x * y
            # where dx is amount in, dy is amount out
            
            # Calculate amount out
            amount_out = (reserve_out * amount_in) / (reserve_in + amount_in)
            
            # Calculate price impact
            price_before = reserve_out / reserve_in
            price_after = (reserve_out - amount_out) / (reserve_in + amount_in)
            price_impact = (price_after - price_before) / price_before
            
            return {
                'amount_in': amount_in,
                'amount_out': amount_out,
                'price_before': price_before,
                'price_after': price_after,
                'price_impact': price_impact,
                'price_impact_bps': price_impact * 10000
            }
            
        except Exception as e:
            logger.error(f"Error calculating price impact: {e}")
            return None
    
    def close(self):
        """Close database connections"""
        if hasattr(self, 'engine'):
            self.engine.dispose()

def main():
    """Test the event parser"""
    console.print("[bold blue]🧪 Testing Event Parser...[/bold blue]")
    
    parser = EventParser()
    
    try:
        # Test with a sample pair (you'll need to have data in the database)
        with parser.Session() as session:
            # Get a sample pair
            result = session.execute(
                text("SELECT pair_address FROM pairs LIMIT 1")
            ).fetchone()
            
            if result:
                pair_address = result[0]
                console.print(f"Testing with pair: {pair_address}")
                
                # Get recent pool state
                pool_state = parser.reconstruct_pool_state(pair_address, 18000000)
                
                if pool_state:
                    console.print("[green]✅ Pool state reconstructed successfully![/green]")
                    console.print(f"Token pair: {pool_state['token0_symbol']}/{pool_state['token1_symbol']}")
                    console.print(f"Price: {pool_state['price_token0_in_token1']:.6f}")
                    console.print(f"Liquidity: ${pool_state['liquidity_usd']:,.2f}")
                else:
                    console.print("[yellow]⚠️ No pool state found for this block[/yellow]")
            else:
                console.print("[yellow]⚠️ No pairs found in database[/yellow]")
                
    except Exception as e:
        console.print(f"[red]❌ Error during testing: {e}[/red]")
    finally:
        parser.close()

if __name__ == "__main__":
    main()
