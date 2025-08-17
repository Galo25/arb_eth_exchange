import argparse
import duckdb
import pandas as pd

def run_verification(parquet_path: str):
    """
    Connects to a Parquet file using DuckDB and runs a series of SQL-based data verification queries.
    """
    print(f"--- Verifying Data Integrity for: {parquet_path} ---")

    try:
        # Use DuckDB to directly query the Parquet file
        con = duckdb.connect(database=':memory:', read_only=False)
        con.execute(f"CREATE OR REPLACE VIEW ohlcv AS SELECT * FROM read_parquet('{parquet_path}');")

        queries = {
            "1. Count Total Records": "SELECT COUNT(*) FROM ohlcv;",
            "2. Time Range": "SELECT MIN(timestamp) AS start_time, MAX(timestamp) AS end_time FROM ohlcv;",
            "3. Check for NULLs": "SELECT COUNT(*) FROM ohlcv WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL;",
            "4. Check for Invalid OHLC (Low > High)": "SELECT COUNT(*) FROM ohlcv WHERE low > high;",
            "5. Check for Zero Volume Bars": "SELECT COUNT(*) FROM ohlcv WHERE volume = 0;",
            "6. Top 5 Volume Bars": "SELECT timestamp, volume FROM ohlcv ORDER BY volume DESC LIMIT 5;",
            "7. Time Gaps (assuming 1-second frequency)": """
                SELECT 
                    COUNT(*) 
                FROM (
                    SELECT 
                        timestamp, 
                        LAG(timestamp, 1) OVER (ORDER BY timestamp) AS prev_timestamp,
                        (EXTRACT(EPOCH FROM timestamp) - EXTRACT(EPOCH FROM LAG(timestamp, 1) OVER (ORDER BY timestamp))) AS diff_seconds
                    FROM ohlcv
                ) AS t 
                WHERE diff_seconds > 1;
            """
        }

        for title, query in queries.items():
            print(f"\n{title}")
            print("-" * (len(title) + 1))
            try:
                result = con.execute(query).fetchdf()
                print(result)
            except Exception as e:
                print(f"Query failed: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'con' in locals():
            con.close()
    
    print("\n--- Verification Complete ---")


def main():
    parser = argparse.ArgumentParser(description="Run SQL-based verification on OHLCV Parquet file.")
    parser.add_argument('parquet_file', type=str, help='Path to the OHLCV Parquet file to verify.')
    args = parser.parse_args()
    
    run_verification(args.parquet_file)

if __name__ == '__main__':
    main()
