"""
Arbitrage Analyzer for DEX Arbitrage Backtesting System

This module analyzes pool states to detect arbitrage opportunities and
simulates trades with realistic costs and constraints.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

class ArbitrageAnalyzer:
    """Analyzes pool states to detect arbitrage opportunities"""
    
    def __init__(self, database_url: str = None, min_spread_bps: int = 50):
        """Initialize the arbitrage analyzer"""
        self.database_url = database_url or 'sqlite:///dex_arbitrage.db'
        self.engine = create_engine(self.database_url, echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self.min_spread_bps = min_spread_bps  # Minimum spread in basis points
        
        # Gas cost estimates (in USD)
        self.gas_price_gwei = 20
        self.gas_limit = 500000
        self.eth_price_usd = 2000  # Approximate
        
        # DEX fees (in basis points)
        self.uniswap_fee_bps = 30  # 0.3%
        self.sushiswap_fee_bps = 30  # 0.3%
        
    def calculate_gas_cost(self, gas_price_gwei: int = None) -> float:
        """Calculate gas cost in USD"""
        gas_price = gas_price_gwei or self.gas_price_gwei
        gas_cost_eth = (gas_price * self.gas_limit * 1e-9)
        gas_cost_usd = gas_cost_eth * self.eth_price_usd
        return gas_cost_usd
    
    def detect_arbitrage_opportunities(self, block_number: int, 
                                     min_spread_bps: int = None) -> List[Dict]:
        """Detect arbitrage opportunities at a specific block"""
        min_spread = min_spread_bps or self.min_spread_bps
        
        try:
            with self.Session() as session:
                # Get all pool states at this block
                query = """
                    SELECT 
                        p.pair_address,
                        p.token0_address,
                        p.token1_address,
                        ex.name as exchange_name,
                        e.reserve0,
                        e.reserve1,
                        e.timestamp,
                        t0.symbol as token0_symbol,
                        t1.symbol as token1_symbol,
                        t0.decimals as token0_decimals,
                        t1.decimals as token1_decimals
                    FROM events_syncs e
                    JOIN pairs p ON e.pair_address = p.pair_address
                    JOIN exchanges ex ON p.exchange_id = ex.exchange_id
                    JOIN tokens t0 ON p.token0_address = t0.token_address
                    JOIN tokens t1 ON p.token1_address = t1.token_address
                    WHERE e.block_number = :block_number
                    ORDER BY e.timestamp DESC
                """
                
                result = session.execute(query, {"block_number": block_number})
                pool_states = [dict(row) for row in result]
                
                if len(pool_states) < 2:
                    return []
                
                # Normalize reserves
                for state in pool_states:
                    state['reserve0_normalized'] = state['reserve0'] / (10 ** state['token0_decimals'])
                    state['reserve1_normalized'] = state['reserve1'] / (10 ** state['token1_decimals'])
                    state['price_token0_in_token1'] = state['reserve1_normalized'] / state['reserve0_normalized']
                
                # Find arbitrage opportunities
                opportunities = []
                
                for i, state1 in enumerate(pool_states):
                    for j, state2 in enumerate(pool_states[i+1:], i+1):
                        # Check if same token pair on different exchanges
                        if (state1['token0_address'] == state2['token0_address'] and 
                            state1['token1_address'] == state2['token1_address'] and
                            state1['exchange_name'] != state2['exchange_name']):
                            
                            # Calculate spread
                            price1 = state1['price_token0_in_token1']
                            price2 = state2['price_token0_in_token1']
                            
                            if price1 != price2:
                                # Determine buy/sell direction
                                if price1 < price2:
                                    buy_state, sell_state = state1, state2
                                    buy_price, sell_price = price1, price2
                                else:
                                    buy_state, sell_state = state2, state1
                                    buy_price, sell_price = price2, price1
                                
                                # Calculate spread in basis points
                                spread_bps = ((sell_price - buy_price) / buy_price) * 10000
                                
                                if spread_bps >= min_spread:
                                    opportunity = {
                                        'block_number': block_number,
                                        'timestamp': state1['timestamp'],
                                        'base_token': state1['token0_symbol'],
                                        'quote_token': state1['token1_symbol'],
                                        'buy_exchange': buy_state['exchange_name'],
                                        'sell_exchange': sell_state['exchange_name'],
                                        'buy_pair_address': buy_state['pair_address'],
                                        'sell_pair_address': sell_state['pair_address'],
                                        'buy_price': buy_price,
                                        'sell_price': sell_price,
                                        'spread_bps': spread_bps,
                                        'spread_percentage': spread_bps / 100,
                                        'buy_reserve0': buy_state['reserve0_normalized'],
                                        'buy_reserve1': buy_state['reserve1_normalized'],
                                        'sell_reserve0': sell_state['reserve0_normalized'],
                                        'sell_reserve1': sell_state['reserve1_normalized']
                                    }
                                    
                                    opportunities.append(opportunity)
                
                return opportunities
                
        except Exception as e:
            logger.error(f"Error detecting arbitrage opportunities: {e}")
            return []
    
    def simulate_arbitrage_trade(self, opportunity: Dict, 
                                trade_amount_base: float = None) -> Dict:
        """Simulate an arbitrage trade with realistic constraints"""
        try:
            # Determine optimal trade amount
            if trade_amount_base is None:
                # Use 10% of the smaller reserve to avoid excessive price impact
                trade_amount_base = min(
                    opportunity['buy_reserve0'] * 0.1,
                    opportunity['sell_reserve0'] * 0.1
                )
            
            # Calculate amounts with fees
            buy_fee_bps = self.get_exchange_fee(opportunity['buy_exchange'])
            sell_fee_bps = self.get_exchange_fee(opportunity['sell_exchange'])
            
            # Amount after buying (accounting for fees)
            buy_fee_multiplier = 1 - (buy_fee_bps / 10000)
            amount_after_buy = trade_amount_base * buy_fee_multiplier
            
            # Amount received after selling (accounting for fees)
            sell_fee_multiplier = 1 - (sell_fee_bps / 10000)
            amount_received = amount_after_buy * opportunity['sell_price'] * sell_fee_multiplier
            
            # Calculate gross profit
            cost_to_buy = trade_amount_base * opportunity['buy_price']
            gross_profit = amount_received - cost_to_buy
            
            # Calculate gas costs
            gas_cost_usd = self.calculate_gas_cost()
            
            # Net profit
            net_profit = gross_profit - gas_cost_usd
            
            # Calculate price impact
            buy_price_impact = self.calculate_price_impact(
                trade_amount_base,
                opportunity['buy_reserve0'],
                opportunity['buy_reserve1']
            )
            
            sell_price_impact = self.calculate_price_impact(
                amount_after_buy,
                opportunity['sell_reserve0'],
                opportunity['sell_reserve1']
            )
            
            # Determine if trade is profitable
            is_profitable = net_profit > 0
            
            # Calculate ROI
            roi = (net_profit / cost_to_buy) * 100 if cost_to_buy > 0 else 0
            
            return {
                'opportunity_id': f"{opportunity['block_number']}_{opportunity['buy_exchange']}_{opportunity['sell_exchange']}",
                'block_number': opportunity['block_number'],
                'timestamp': opportunity['timestamp'],
                'base_token': opportunity['base_token'],
                'quote_token': opportunity['quote_token'],
                'buy_exchange': opportunity['buy_exchange'],
                'sell_exchange': opportunity['sell_exchange'],
                'trade_amount_base': trade_amount_base,
                'buy_price': opportunity['buy_price'],
                'sell_price': opportunity['sell_price'],
                'spread_bps': opportunity['spread_bps'],
                'gross_profit': gross_profit,
                'gas_cost_usd': gas_cost_usd,
                'net_profit': net_profit,
                'is_profitable': is_profitable,
                'roi_percentage': roi,
                'buy_fee_bps': buy_fee_bps,
                'sell_fee_bps': sell_fee_bps,
                'buy_price_impact_bps': buy_price_impact['price_impact_bps'] if buy_price_impact else 0,
                'sell_price_impact_bps': sell_price_impact['price_impact_bps'] if sell_price_impact else 0,
                'execution_notes': self.generate_execution_notes(opportunity, is_profitable)
            }
            
        except Exception as e:
            logger.error(f"Error simulating arbitrage trade: {e}")
            return None
    
    def get_exchange_fee(self, exchange_name: str) -> int:
        """Get fee for a specific exchange in basis points"""
        fees = {
            'Uniswap V2': self.uniswap_fee_bps,
            'SushiSwap': self.sushiswap_fee_bps
        }
        return fees.get(exchange_name, 30)  # Default to 0.3%
    
    def calculate_price_impact(self, amount_in: float, reserve_in: float, 
                              reserve_out: float) -> Optional[Dict]:
        """Calculate price impact using constant product AMM formula"""
        try:
            if reserve_in == 0 or reserve_out == 0:
                return None
            
            # Constant product formula: (x + dx) * (y - dy) = x * y
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
    
    def generate_execution_notes(self, opportunity: Dict, is_profitable: bool) -> str:
        """Generate execution notes for the trade"""
        if is_profitable:
            return f"Profitable arbitrage: {opportunity['spread_bps']:.1f} bps spread"
        else:
            return f"Unprofitable due to gas costs: {opportunity['spread_bps']:.1f} bps spread too small"
    
    def analyze_historical_opportunities(self, from_block: int, to_block: int,
                                       min_spread_bps: int = None) -> pd.DataFrame:
        """Analyze arbitrage opportunities over a block range"""
        min_spread = min_spread_bps or self.min_spread_bps
        
        console.print(f"[bold blue]🔍 Analyzing arbitrage opportunities from block {from_block:,} to {to_block:,}[/bold blue]")
        
        all_opportunities = []
        all_trades = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            
            task = progress.add_task(
                f"Analyzing blocks {from_block:,} to {to_block:,}",
                total=to_block - from_block
            )
            
            for block_number in range(from_block, to_block + 1):
                try:
                    # Detect opportunities at this block
                    opportunities = self.detect_arbitrage_opportunities(block_number, min_spread)
                    
                    for opportunity in opportunities:
                        all_opportunities.append(opportunity)
                        
                        # Simulate trade
                        trade_simulation = self.simulate_arbitrage_trade(opportunity)
                        if trade_simulation:
                            all_trades.append(trade_simulation)
                    
                    # Update progress every 100 blocks
                    if (block_number - from_block) % 100 == 0:
                        progress.update(task, completed=block_number - from_block)
                        
                except Exception as e:
                    logger.warning(f"Error analyzing block {block_number}: {e}")
                    continue
        
        # Convert to DataFrames
        df_opportunities = pd.DataFrame(all_opportunities)
        df_trades = pd.DataFrame(all_trades)
        
        console.print(f"[green]✅ Analysis complete! Found {len(all_opportunities):,} opportunities and {len(all_trades):,} trades[/green]")
        
        return df_opportunities, df_trades
    
    def get_opportunity_summary(self, df_opportunities: pd.DataFrame, 
                               df_trades: pd.DataFrame) -> Dict:
        """Generate summary statistics for opportunities and trades"""
        try:
            summary = {
                'total_opportunities': len(df_opportunities),
                'total_trades': len(df_trades),
                'profitable_trades': len(df_trades[df_trades['is_profitable'] == True]),
                'profitable_rate': len(df_trades[df_trades['is_profitable'] == True]) / len(df_trades) if len(df_trades) > 0 else 0,
                'avg_spread_bps': df_opportunities['spread_bps'].mean() if len(df_opportunities) > 0 else 0,
                'max_spread_bps': df_opportunities['spread_bps'].max() if len(df_opportunities) > 0 else 0,
                'total_gross_profit': df_trades['gross_profit'].sum() if len(df_trades) > 0 else 0,
                'total_net_profit': df_trades['net_profit'].sum() if len(df_trades) > 0 else 0,
                'total_gas_costs': df_trades['gas_cost_usd'].sum() if len(df_trades) > 0 else 0,
                'avg_roi': df_trades['roi_percentage'].mean() if len(df_trades) > 0 else 0
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {}
    
    def close(self):
        """Close database connections"""
        if hasattr(self, 'engine'):
            self.engine.dispose()

def main():
    """Test the arbitrage analyzer"""
    console.print("[bold blue]🧪 Testing Arbitrage Analyzer...[/bold blue]")
    
    analyzer = ArbitrageAnalyzer()
    
    try:
        # Test with a small block range
        from_block = 18000000
        to_block = 18000100
        
        console.print(f"Testing with blocks {from_block:,} to {to_block:,}")
        
        # Analyze opportunities
        df_opps, df_trades = analyzer.analyze_historical_opportunities(
            from_block, to_block, min_spread_bps=50
        )
        
        if len(df_opps) > 0:
            console.print("[green]✅ Opportunities found![/green]")
            console.print(f"Total opportunities: {len(df_opps):,}")
            console.print(f"Total trades simulated: {len(df_trades):,}")
            
            # Show summary
            summary = analyzer.get_opportunity_summary(df_opps, df_trades)
            console.print("\n[bold blue]📊 Summary Statistics:[/bold blue]")
            for key, value in summary.items():
                if isinstance(value, float):
                    console.print(f"  {key}: {value:.2f}")
                else:
                    console.print(f"  {key}: {value:,}")
        else:
            console.print("[yellow]⚠️ No opportunities found in this block range[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ Error during testing: {e}[/red]")
    finally:
        analyzer.close()

if __name__ == "__main__":
    main()
