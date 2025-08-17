# 🚀 **DEX Arbitrage Backtesting System**

## 🎯 **Project Overview**

A comprehensive historical arbitrage simulation engine for decentralized exchanges (DEXs) that reconstructs past pool states from on-chain data to detect and simulate arbitrage opportunities.

## 🏗 **Architecture Overview**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Etherscan     │    │   Data Fetcher  │    │   Event Parser  │
│     API         │───▶│   (Rate Limit)  │───▶│   (Normalize)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Database      │◀───│   Analyzer      │◀───│   Pool State    │
│   (Results)     │    │   (Arbitrage)   │    │   Calculator    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🛠 **Technical Stack**

- **Data Source**: Etherscan API
- **Database**: PostgreSQL/SQLite
- **Language**: Python 3.9+
- **Key Libraries**: web3.py, pandas, sqlalchemy
- **Target Chains**: Ethereum Mainnet
- **Target DEXs**: Uniswap V2, SushiSwap

## 📊 **Data Schema**

### **Reference Tables**
```sql
-- Exchanges (DEXs)
CREATE TABLE exchanges (
    exchange_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    router_address CHAR(42) NOT NULL,
    factory_address CHAR(42) NOT NULL,
    chain_id INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tokens
CREATE TABLE tokens (
    token_address CHAR(42) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    decimals INTEGER NOT NULL,
    chain_id INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trading Pairs
CREATE TABLE pairs (
    pair_address CHAR(42) PRIMARY KEY,
    token0_address CHAR(42) REFERENCES tokens(token_address),
    token1_address CHAR(42) REFERENCES tokens(token_address),
    exchange_id INTEGER REFERENCES exchanges(exchange_id),
    fee_bps INTEGER NOT NULL, -- 30 = 0.3%
    created_block BIGINT NOT NULL,
    chain_id INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### **Event Tables**
```sql
-- Swap Events
CREATE TABLE events_swaps (
    id SERIAL PRIMARY KEY,
    pair_address CHAR(42) REFERENCES pairs(pair_address),
    block_number BIGINT NOT NULL,
    tx_hash CHAR(66) NOT NULL,
    log_index INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    sender CHAR(42) NOT NULL,
    to_address CHAR(42) NOT NULL,
    amount0_in NUMERIC(78,0),
    amount1_in NUMERIC(78,0),
    amount0_out NUMERIC(78,0),
    amount1_out NUMERIC(78,0),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sync Events (Reserve Updates)
CREATE TABLE events_syncs (
    id SERIAL PRIMARY KEY,
    pair_address CHAR(42) REFERENCES pairs(pair_address),
    block_number BIGINT NOT NULL,
    tx_hash CHAR(66) NOT NULL,
    log_index INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    reserve0 NUMERIC(78,0) NOT NULL,
    reserve1 NUMERIC(78,0) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### **Derived Views**
```sql
-- Pool State by Block
CREATE VIEW pair_state_by_block AS
SELECT 
    p.pair_address,
    e.block_number,
    e.timestamp,
    e.reserve0 / POWER(10, t0.decimals) AS reserve0_adj,
    e.reserve1 / POWER(10, t1.decimals) AS reserve1_adj,
    e.reserve1 / e.reserve0 AS price_token0_in_token1,
    e.reserve0 / e.reserve1 AS price_token1_in_token0
FROM events_syncs e
JOIN pairs p ON e.pair_address = p.pair_address
JOIN tokens t0 ON p.token0_address = t0.token_address
JOIN tokens t1 ON p.token1_address = t1.token_address;

-- Arbitrage Opportunities
CREATE VIEW arb_opportunities AS
SELECT 
    b1.block_number,
    b1.timestamp,
    t0.symbol AS base_token,
    t1.symbol AS quote_token,
    ex1.name AS buy_exchange,
    ex2.name AS sell_exchange,
    b1.price_token0_in_token1 AS buy_price,
    b2.price_token0_in_token1 AS sell_price,
    ((b2.price_token0_in_token1 - b1.price_token0_in_token1) / b1.price_token0_in_token1 * 10000) AS spread_bps,
    LEAST(b1.reserve0_adj, b2.reserve0_adj) * 0.1 AS est_fill_amount_base
FROM pair_state_by_block b1
JOIN pair_state_by_block b2 ON b1.block_number = b2.block_number 
    AND b1.pair_address != b2.pair_address
JOIN pairs p1 ON b1.pair_address = p1.pair_address
JOIN pairs p2 ON b2.pair_address = p2.pair_address
JOIN exchanges ex1 ON p1.exchange_id = ex1.exchange_id
JOIN exchanges ex2 ON p2.exchange_id = ex2.exchange_id
JOIN tokens t0 ON p1.token0_address = t0.token_address
JOIN tokens t1 ON p1.token1_address = t1.token_address
WHERE b1.price_token0_in_token1 < b2.price_token0_in_token1
    AND ((b2.price_token0_in_token1 - b1.price_token0_in_token1) / b1.price_token0_in_token1 * 10000) > 50; -- 0.5% minimum spread
```

## 🔧 **Setup Instructions**

### **1. Environment Setup**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### **2. Configuration**
```bash
# Copy and configure environment
cp .env.example .env

# Set your Etherscan API key
ETHERSCAN_API_KEY=1BHRB44DM7HPSSZ4KWEM3RGUB4I9GRKPHD
```

### **3. Database Setup**
```bash
# Initialize database
python scripts/setup_database.py

# Run migrations
python scripts/migrate.py
```

### **4. Data Collection**
```bash
# Start data collection
python scripts/fetch_etherscan_data.py --start-block 15000000 --end-block 15001000

# Parse events
python scripts/parse_events.py

# Analyze arbitrage opportunities
python scripts/analyze_arbitrage.py
```

## 📈 **Usage Examples**

### **Fetch Historical Data**
```python
from fetcher import EtherscanFetcher

fetcher = EtherscanFetcher(api_key="your_key")
events = fetcher.fetch_swap_events(
    contract_address="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2 Router
    start_block=15000000,
    end_block=15001000
)
```

### **Parse Pool States**
```python
from parser import EventParser

parser = EventParser()
pool_states = parser.reconstruct_pool_states(events)
```

### **Detect Arbitrage**
```python
from analyzer import ArbitrageAnalyzer

analyzer = ArbitrageAnalyzer()
opportunities = analyzer.find_arbitrage_opportunities(
    pool_states,
    min_spread_bps=50  # 0.5% minimum spread
)
```

## 🎯 **Phase 1 Goals**

- [x] **Database Schema Design**
- [ ] **Etherscan Data Fetcher**
- [ ] **Event Parser Implementation**
- [ ] **Pool State Reconstruction**
- [ ] **Arbitrage Detection Algorithm**
- [ ] **Historical Simulation Engine**
- [ ] **Validation Framework**

## 🚀 **Phase 2 Roadmap**

- **Real-time Data**: Switch from Etherscan to Node Providers
- **Multi-chain Support**: Polygon, BSC, Arbitrum
- **Advanced DEXs**: Uniswap V3, Curve, Balancer
- **MEV Protection**: Flash loan simulation with gas optimization
- **Live Trading**: Integration with wallet providers

## 📊 **Expected Results**

### **Historical Analysis**
- **Time Period**: Last 6 months of Ethereum mainnet
- **Data Volume**: ~100GB of event data
- **Opportunities**: 1000+ arbitrage instances detected
- **Profitability**: Net profit after gas costs analysis

### **Validation Metrics**
- **Accuracy**: Cross-check with DexScreener
- **Performance**: Sub-second opportunity detection
- **Scalability**: Handle 1000+ pairs simultaneously

## ⚠️ **Important Notes**

1. **Rate Limits**: Etherscan API has strict rate limits (5 calls/second)
2. **Gas Costs**: All simulations include realistic gas estimates
3. **Slippage**: Price impact calculations use constant-product AMM formulas
4. **Flash Loans**: Simulations assume successful flash loan execution

## 🔗 **Useful Links**

- [Etherscan API Documentation](https://docs.etherscan.io/)
- [Uniswap V2 Documentation](https://docs.uniswap.org/protocol/V2/introduction)
- [DexScreener API](https://docs.dexscreener.com/api/reference)
- [Web3.py Documentation](https://web3py.readthedocs.io/)

---

**Ready to build the future of DEX arbitrage backtesting!** 🚀
