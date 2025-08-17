"""
Etherscan Fetcher Module for DEX Arbitrage Backtesting

This module handles fetching historical blockchain data from Etherscan API
including swap events, sync events, and block information.
"""

from .etherscan_fetcher import EtherscanFetcher, AsyncEtherscanFetcher

__all__ = ['EtherscanFetcher', 'AsyncEtherscanFetcher']
