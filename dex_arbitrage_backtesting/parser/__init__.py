"""
Event Parser Module for DEX Arbitrage Backtesting

This module handles parsing and normalizing blockchain events to reconstruct
pool states and calculate prices for arbitrage analysis.
"""

from .event_parser import EventParser

__all__ = ['EventParser']
