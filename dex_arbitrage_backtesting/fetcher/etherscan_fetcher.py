"""
Etherscan Data Fetcher for DEX Arbitrage Backtesting

This module handles fetching historical blockchain data from Etherscan API
including swap events, sync events, and block information.
"""

import requests
import time
import asyncio
import aiohttp
from typing import List, Dict, Optional, Generator
from datetime import datetime
import os
from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

class EtherscanFetcher:
    """Fetches data from Etherscan API with rate limiting"""
    
    def __init__(self, api_key: str = None, base_url: str = "https://api.etherscan.io/api"):
        self.api_key = api_key or os.getenv('ETHERSCAN_API_KEY')
        if not self.api_key:
            raise ValueError("Etherscan API key is required")
        
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DEX-Arbitrage-Backtesting/1.0'
        })
        
        # Rate limiting: 5 calls/second
        self.rate_limit = 5
        self.last_call_time = 0
        
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_call_time
        min_interval = 1.0 / self.rate_limit
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()
    
    def _make_request(self, params: Dict) -> Dict:
        """Make a single API request with rate limiting"""
        self._rate_limit()
        
        params['apikey'] = self.api_key
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == '0':
                error_msg = data.get('message', 'Unknown error')
                logger.error(f"Etherscan API error: {error_msg}")
                raise Exception(f"Etherscan API error: {error_msg}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
    
    def get_block_by_number(self, block_number: int) -> Optional[Dict]:
        """Get block information by block number"""
        params = {
            'module': 'proxy',
            'action': 'eth_getBlockByNumber',
            'tag': hex(block_number),
            'boolean': 'false'
        }
        
        data = self._make_request(params)
        return data.get('result')
    
    def get_block_timestamp(self, block_number: int) -> Optional[int]:
        """Get block timestamp by block number"""
        block = self.get_block_by_number(block_number)
        if block and block.get('timestamp'):
            return int(block['timestamp'], 16)
        return None
    
    def get_logs(self, 
                 address: str,
                 from_block: int,
                 to_block: int,
                 topics: List[str] = None,
                 page: int = 1,
                 offset: int = 1000) -> Dict:
        """Get event logs from a contract address"""
        params = {
            'module': 'logs',
            'action': 'getLogs',
            'address': address,
            'fromBlock': from_block,
            'toBlock': to_block,
            'page': page,
            'offset': offset
        }
        
        if topics:
            for i, topic in enumerate(topics):
                params[f'topic{i}'] = topic
        
        return self._make_request(params)
    
    def get_swap_events(self, 
                        router_address: str,
                        from_block: int,
                        to_block: int,
                        batch_size: int = 1000) -> Generator[Dict, None, None]:
        """Get swap events from a DEX router contract"""
        
        # Uniswap V2 Swap event signature
        swap_topic = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
        
        current_block = from_block
        
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
            
            while current_block < to_block:
                end_block = min(current_block + batch_size - 1, to_block)
                
                try:
                    logs = self.get_logs(
                        address=router_address,
                        from_block=current_block,
                        to_block=end_block,
                        topics=[swap_topic]
                    )
                    
                    if logs.get('result'):
                        for log in logs['result']:
                            # Parse swap event data
                            parsed_event = self._parse_swap_event(log)
                            if parsed_event:
                                yield parsed_event
                    
                    progress.update(task, completed=end_block - from_block)
                    current_block = end_block + 1
                    
                except Exception as e:
                    logger.error(f"Error fetching logs for blocks {current_block}-{end_block}: {e}")
                    # Continue with next batch
                    current_block = end_block + 1
                    continue
    
    def get_sync_events(self,
                        pair_address: str,
                        from_block: int,
                        to_block: int,
                        batch_size: int = 1000) -> Generator[Dict, None, None]:
        """Get sync events (reserve updates) from a pair contract"""
        
        # Sync event signature
        sync_topic = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
        
        current_block = from_block
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            
            task = progress.add_task(
                f"Fetching sync events for pair {pair_address[:10]}...",
                total=to_block - from_block
            )
            
            while current_block < to_block:
                end_block = min(current_block + batch_size - 1, to_block)
                
                try:
                    logs = self.get_logs(
                        address=pair_address,
                        from_block=current_block,
                        to_block=end_block,
                        topics=[sync_topic]
                    )
                    
                    if logs.get('result'):
                        for log in logs['result']:
                            # Parse sync event data
                            parsed_event = self._parse_sync_event(log)
                            if parsed_event:
                                yield parsed_event
                    
                    progress.update(task, completed=end_block - from_block)
                    current_block = end_block + 1
                    
                except Exception as e:
                    logger.error(f"Error fetching sync logs for blocks {current_block}-{end_block}: {e}")
                    current_block = end_block + 1
                    continue
    
    def _parse_swap_event(self, log: Dict) -> Optional[Dict]:
        """Parse a swap event log into structured data"""
        try:
            # Get block timestamp
            block_number = int(log['blockNumber'], 16)
            timestamp = self.get_block_timestamp(block_number)
            
            if not timestamp:
                logger.warning(f"Could not get timestamp for block {block_number}")
                return None
            
            # Parse topics and data
            topics = log['topics']
            data = log['data']
            
            # Swap event has 3 topics: [event_signature, sender, to]
            if len(topics) < 3:
                logger.warning(f"Invalid swap event format: {log}")
                return None
            
            sender = topics[1][-40:]  # Remove 0x prefix
            to_address = topics[2][-40:]
            
            # Parse amounts from data (amount0In, amount1In, amount0Out, amount1Out)
            # Each amount is 32 bytes (64 hex chars)
            if len(data) < 258:  # 0x + 4 * 64
                logger.warning(f"Invalid swap event data length: {len(data)}")
                return None
            
            data = data[2:]  # Remove 0x prefix
            
            amount0_in = int(data[0:64], 16)
            amount1_in = int(data[64:128], 16)
            amount0_out = int(data[128:192], 16)
            amount1_out = int(data[192:256], 16)
            
            return {
                'pair_address': log['address'],
                'block_number': block_number,
                'tx_hash': log['transactionHash'],
                'log_index': int(log['logIndex'], 16),
                'timestamp': datetime.fromtimestamp(timestamp),
                'sender': f"0x{sender}",
                'to_address': f"0x{to_address}",
                'amount0_in': amount0_in,
                'amount1_in': amount1_in,
                'amount0_out': amount0_out,
                'amount1_out': amount1_out
            }
            
        except Exception as e:
            logger.error(f"Error parsing swap event: {e}")
            return None
    
    def _parse_sync_event(self, log: Dict) -> Optional[Dict]:
        """Parse a sync event log into structured data"""
        try:
            # Get block timestamp
            block_number = int(log['blockNumber'], 16)
            timestamp = self.get_block_timestamp(block_number)
            
            if not timestamp:
                logger.warning(f"Could not get timestamp for block {block_number}")
                return None
            
            # Parse data (reserve0, reserve1)
            data = log['data']
            if len(data) < 130:  # 0x + 2 * 64
                logger.warning(f"Invalid sync event data length: {len(data)}")
                return None
            
            data = data[2:]  # Remove 0x prefix
            
            reserve0 = int(data[0:64], 16)
            reserve1 = int(data[64:128], 16)
            
            return {
                'pair_address': log['address'],
                'block_number': block_number,
                'tx_hash': log['transactionHash'],
                'log_index': int(log['logIndex'], 16),
                'timestamp': datetime.fromtimestamp(timestamp),
                'reserve0': reserve0,
                'reserve1': reserve1
            }
            
        except Exception as e:
            logger.error(f"Error parsing sync event: {e}")
            return None
    
    def get_contract_abi(self, contract_address: str) -> Optional[str]:
        """Get contract ABI from Etherscan"""
        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': contract_address
        }
        
        data = self._make_request(params)
        return data.get('result')
    
    def get_token_info(self, token_address: str) -> Optional[Dict]:
        """Get token information from Etherscan"""
        # Try to get from contract source
        params = {
            'module': 'contract',
            'action': 'getsourcecode',
            'address': token_address
        }
        
        data = self._make_request(params)
        result = data.get('result', [{}])[0]
        
        if result.get('SourceCode'):
            # Parse source code for token info
            return self._parse_token_source(result['SourceCode'])
        
        return None
    
    def _parse_token_source(self, source_code: str) -> Optional[Dict]:
        """Parse token source code for basic information"""
        # This is a simplified parser - in production you might want more sophisticated parsing
        try:
            # Look for common patterns in ERC-20 contracts
            if 'function name()' in source_code and 'function symbol()' in source_code:
                return {
                    'has_source': True,
                    'is_verified': True
                }
        except Exception as e:
            logger.warning(f"Error parsing token source: {e}")
        
        return None
    
    def close(self):
        """Close the session"""
        if self.session:
            self.session.close()

class AsyncEtherscanFetcher(EtherscanFetcher):
    """Async version of EtherscanFetcher for better performance"""
    
    def __init__(self, api_key: str = None, base_url: str = "https://api.etherscan.io/api"):
        super().__init__(api_key, base_url)
        self.session = None  # Will be created in async context
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _make_request_async(self, params: Dict) -> Dict:
        """Make async API request"""
        # Implement async rate limiting
        await asyncio.sleep(1.0 / self.rate_limit)
        
        params['apikey'] = self.api_key
        
        try:
            async with self.session.get(self.base_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                if data.get('status') == '0':
                    error_msg = data.get('message', 'Unknown error')
                    raise Exception(f"Etherscan API error: {error_msg}")
                
                return data
                
        except Exception as e:
            logger.error(f"Async request failed: {e}")
            raise

if __name__ == "__main__":
    # Example usage
    fetcher = EtherscanFetcher()
    
    try:
        # Test fetching swap events from Uniswap V2 Router
        uniswap_router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        
        print("Fetching recent swap events...")
        events = list(fetcher.get_swap_events(
            router_address=uniswap_router,
            from_block=18000000,  # Recent block
            to_block=18000100,    # Small range for testing
            batch_size=100
        ))
        
        print(f"Found {len(events)} swap events")
        for event in events[:3]:  # Show first 3
            print(f"  {event['timestamp']}: {event['amount0_in']} -> {event['amount0_out']}")
            
    finally:
        fetcher.close()
