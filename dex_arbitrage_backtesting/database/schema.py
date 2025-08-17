"""
Database Schema for DEX Arbitrage Backtesting System

This module defines the complete database schema including:
- Reference tables (exchanges, tokens, pairs)
- Event tables (swaps, syncs)
- Derived views for analysis
"""

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, 
    BigInteger, Numeric, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import text
from datetime import datetime
import os

Base = declarative_base()

class Exchange(Base):
    """DEX Exchange information"""
    __tablename__ = 'exchanges'
    
    exchange_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    router_address = Column(String(42), nullable=False)  # 0x... format
    factory_address = Column(String(42), nullable=False)
    chain_id = Column(Integer, default=1)  # 1 = Ethereum mainnet
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    pairs = relationship("Pair", back_populates="exchange")
    
    def __repr__(self):
        return f"<Exchange(name='{self.name}', chain_id={self.chain_id})>"

class Token(Base):
    """ERC-20 Token information"""
    __tablename__ = 'tokens'
    
    token_address = Column(String(42), primary_key=True)  # 0x... format
    symbol = Column(String(20), nullable=False)
    decimals = Column(Integer, nullable=False)
    chain_id = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    token0_pairs = relationship("Pair", foreign_keys="Pair.token0_address", back_populates="token0")
    token1_pairs = relationship("Pair", foreign_keys="Pair.token1_address", back_populates="token1")
    
    def __repr__(self):
        return f"<Token(symbol='{self.symbol}', decimals={self.decimals})>"

class Pair(Base):
    """Trading pair information"""
    __tablename__ = 'pairs'
    
    pair_address = Column(String(42), primary_key=True)  # 0x... format
    token0_address = Column(String(42), ForeignKey('tokens.token_address'), nullable=False)
    token1_address = Column(String(42), ForeignKey('tokens.token_address'), nullable=False)
    exchange_id = Column(Integer, ForeignKey('exchanges.exchange_id'), nullable=False)
    fee_bps = Column(Integer, nullable=False)  # 30 = 0.3%
    created_block = Column(BigInteger, nullable=False)
    chain_id = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    exchange = relationship("Exchange", back_populates="pairs")
    token0 = relationship("Token", foreign_keys=[token0_address], back_populates="token0_pairs")
    token1 = relationship("Token", foreign_keys=[token1_address], back_populates="token1_pairs")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_pair_exchange', 'exchange_id'),
        Index('idx_pair_tokens', 'token0_address', 'token1_address'),
        Index('idx_pair_chain', 'chain_id'),
    )
    
    def __repr__(self):
        return f"<Pair({self.token0.symbol}/{self.token1.symbol} on {self.exchange.name})>"

class EventSwap(Base):
    """Swap event from DEX"""
    __tablename__ = 'events_swaps'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_address = Column(String(42), ForeignKey('pairs.pair_address'), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    tx_hash = Column(String(66), nullable=False)  # 0x... format
    log_index = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    sender = Column(String(42), nullable=False)
    to_address = Column(String(42), nullable=False)
    amount0_in = Column(Numeric(78, 0))  # Raw token amounts
    amount1_in = Column(Numeric(78, 0))
    amount0_out = Column(Numeric(78, 0))
    amount1_out = Column(Numeric(78, 0))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    pair = relationship("Pair")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_swap_pair_block', 'pair_address', 'block_number'),
        Index('idx_swap_timestamp', 'timestamp'),
        Index('idx_swap_tx_hash', 'tx_hash'),
    )
    
    def __repr__(self):
        return f"<EventSwap(pair={self.pair_address}, block={self.block_number})>"

class EventSync(Base):
    """Sync event (reserve update) from DEX"""
    __tablename__ = 'events_syncs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_address = Column(String(42), ForeignKey('pairs.pair_address'), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    tx_hash = Column(String(66), nullable=False)
    log_index = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    reserve0 = Column(Numeric(78, 0), nullable=False)  # Raw token reserves
    reserve1 = Column(Numeric(78, 0), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    pair = relationship("Pair")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_sync_pair_block', 'pair_address', 'block_number'),
        Index('idx_sync_timestamp', 'timestamp'),
        Index('idx_sync_tx_hash', 'tx_hash'),
    )
    
    def __repr__(self):
        return f"<EventSync(pair={self.pair_address}, block={self.block_number})>"

class Block(Base):
    """Block information (optional, for validation)"""
    __tablename__ = 'blocks'
    
    block_number = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    gas_used = Column(BigInteger)
    gas_limit = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Block(number={self.block_number}, timestamp={self.timestamp})>"

def create_tables(engine):
    """Create all tables in the database"""
    Base.metadata.create_all(engine)
    print("✅ Database tables created successfully")

def create_views(engine):
    """Create derived views for analysis"""
    views = {
        'pair_state_by_block': """
        CREATE VIEW pair_state_by_block AS
        SELECT 
            p.pair_address,
            e.block_number,
            e.timestamp,
            e.reserve0 / POWER(10, t0.decimals) AS reserve0_adj,
            e.reserve1 / POWER(10, t1.decimals) AS reserve1_adj,
            e.reserve1 / e.reserve0 AS price_token0_in_token1,
            e.reserve0 / e.reserve1 AS price_token1_in_token0,
            ex.name AS exchange_name,
            t0.symbol AS token0_symbol,
            t1.symbol AS token1_symbol
        FROM events_syncs e
        JOIN pairs p ON e.pair_address = p.pair_address
        JOIN exchanges ex ON p.exchange_id = ex.exchange_id
        JOIN tokens t0 ON p.token0_address = t0.token_address
        JOIN tokens t1 ON p.token1_address = t1.token_address
        """,
        
        'arb_opportunities': """
        CREATE VIEW arb_opportunities AS
        SELECT 
            b1.block_number,
            b1.timestamp,
            b1.token0_symbol AS base_token,
            b1.token1_symbol AS quote_token,
            b1.exchange_name AS buy_exchange,
            b2.exchange_name AS sell_exchange,
            b1.price_token0_in_token1 AS buy_price,
            b2.price_token0_in_token1 AS sell_price,
            ((b2.price_token0_in_token1 - b1.price_token0_in_token1) / b1.price_token0_in_token1 * 10000) AS spread_bps,
            LEAST(b1.reserve0_adj, b2.reserve0_adj) * 0.1 AS est_fill_amount_base,
            b1.pair_address AS buy_pair,
            b2.pair_address AS sell_pair
        FROM pair_state_by_block b1
        JOIN pair_state_by_block b2 ON b1.block_number = b2.block_number 
            AND b1.pair_address != b2.pair_address
            AND b1.token0_symbol = b2.token0_symbol
            AND b1.token1_symbol = b2.token1_symbol
        WHERE b1.price_token0_in_token1 < b2.price_token0_in_token1
            AND ((b2.price_token0_in_token1 - b1.price_token0_in_token1) / b1.price_token0_in_token1 * 10000) > 50
        ORDER BY spread_bps DESC
        """
    }
    
    with engine.connect() as conn:
        for view_name, view_sql in views.items():
            try:
                conn.execute(text(f"DROP VIEW IF EXISTS {view_name}"))
                conn.execute(text(view_sql))
                conn.commit()
                print(f"✅ View '{view_name}' created successfully")
            except Exception as e:
                print(f"❌ Error creating view '{view_name}': {e}")

def insert_initial_data(session):
    """Insert initial reference data"""
    
    # Insert major DEXs
    exchanges = [
        {
            'name': 'Uniswap V2',
            'router_address': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
            'chain_id': 1
        },
        {
            'name': 'SushiSwap',
            'router_address': '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',
            'factory_address': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
            'chain_id': 1
        }
    ]
    
    for exchange_data in exchanges:
        exchange = Exchange(**exchange_data)
        session.add(exchange)
    
    # Insert major tokens
    tokens = [
        {
            'token_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            'symbol': 'WETH',
            'decimals': 18,
            'chain_id': 1
        },
        {
            'token_address': '0xA0b86a33E6441b8c4C8B0b8c4C8B0b8c4C8B0b8c',  # USDC
            'symbol': 'USDC',
            'decimals': 6,
            'chain_id': 1
        },
        {
            'token_address': '0xdAC17F958D2ee523a2206206994597C13D831ec7',  # USDT
            'symbol': 'USDT',
            'decimals': 6,
            'chain_id': 1
        }
    ]
    
    for token_data in tokens:
        token = Token(**token_data)
        session.add(token)
    
    try:
        session.commit()
        print("✅ Initial reference data inserted successfully")
    except Exception as e:
        session.rollback()
        print(f"❌ Error inserting initial data: {e}")

def get_database_url():
    """Get database URL from environment or use default SQLite"""
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url
    
    # Default to SQLite for development
    return 'sqlite:///dex_arbitrage.db'

def create_database():
    """Create database with all tables and views"""
    db_url = get_database_url()
    engine = create_engine(db_url, echo=False)
    
    # Create tables
    create_tables(engine)
    
    # Create views
    create_views(engine)
    
    # Create session and insert initial data
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        insert_initial_data(session)
    finally:
        session.close()
    
    print(f"✅ Database created successfully at: {db_url}")
    return engine

if __name__ == "__main__":
    create_database()
