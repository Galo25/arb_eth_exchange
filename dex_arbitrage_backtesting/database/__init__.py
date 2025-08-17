"""
Database Module for DEX Arbitrage Backtesting

This module defines the complete database schema including:
- Reference tables (exchanges, tokens, pairs)
- Event tables (swaps, syncs)
- Derived views for analysis
"""

from .schema import (
    Base, Exchange, Token, Pair, EventSwap, EventSync, Block,
    create_tables, create_views, insert_initial_data, create_database,
    get_database_url
)

__all__ = [
    'Base', 'Exchange', 'Token', 'Pair', 'EventSwap', 'EventSync', 'Block',
    'create_tables', 'create_views', 'insert_initial_data', 'create_database',
    'get_database_url'
]
