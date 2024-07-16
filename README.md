# Financial Data Platform

## Project Overview
 The purpose of this project is to develop a system for ingesting real-time and historical data from IBKR, aggregating it, creating backtest strategies based on various indicators, integrating with Schwab for paper and live trading, and developing a user interface for interaction.


## Setup Process and Initial Configuration Steps

### 1. Setting Up the Git Repository

The Git repository for the project was set up and can be accessed [here](https://github.com/mehdfaisal/financial-data-platform).

### 2. Setting Up the Development Environment

1. **Created and Activated a Virtual Environment:**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

2. **Installed Required Libraries:**
    ```sh
    pip install ib_insync pandas ta-lib pyarrow psycopg2 selenium
    ```

### 3. Setting Up PostgreSQL

1. **Installed PostgreSQL**:
    - Downloaded and installed PostgreSQL from the [official website](https://www.postgresql.org/download/).

2. **Installed pgAdmin4**:
    - Downloaded and installed pgAdmin4 from the [official website](https://www.pgadmin.org/download/).

3. **Created a Database**:
    - Opened pgAdmin4 and connected to the PostgreSQL server.
    - Right-clicked on the "Databases" node and selected "Create" > "Database...".
    - Named the database `financial_data`.

4. **Created Necessary Tables**:
    - Opened the Query Tool in pgAdmin4 and ran the following SQL script:

    ```sql
    CREATE TABLE ohlcv (
        datetime TIMESTAMPTZ NOT NULL,
        open NUMERIC,
        high NUMERIC,
        low NUMERIC,
        close NUMERIC,
        volume NUMERIC,
        symbol VARCHAR(10)
    );

    CREATE TABLE indicators (
        datetime TIMESTAMPTZ NOT NULL,
        symbol VARCHAR(10),
        indicator_name VARCHAR(50),
        indicator_value NUMERIC
    );

    CREATE TABLE trades (
        trade_id SERIAL PRIMARY KEY,
        datetime TIMESTAMPTZ NOT NULL,
        symbol VARCHAR(10),
        trade_type VARCHAR(10),
        price NUMERIC,
        volume NUMERIC
    );
    ```

### 4. Fetching Historical Data

A basic script was written to connect to IBKR and fetch historical data. Below is the sample script used:

```python
import ib_insync
import pandas as pd
from common import save_to_postgresql

def connect_to_ibkr():
    ib = ib_insync.IB()
    ib.connect('127.0.0.1', 7497, clientId=1)
    return ib

def fetch_historical_data_ibkr(symbol):
    ib = connect_to_ibkr()
    contract = ib_insync.Stock(symbol, 'SMART', 'USD')
    
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.DateOffset(months=5)
    
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_date,
        durationStr='5 M',
        barSizeSetting='5 mins',
        whatToShow='TRADES',
        useRTH=True
    )
    
    ib.disconnect()
    
    df = pd.DataFrame(bars)
    return df

def main():
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    for symbol in symbols:
        df = fetch_historical_data_ibkr(symbol)
        save_to_postgresql(df, 'ohlcv', 'financial_data', 'your_username', 'your_password', 'localhost')

if __name__ == "__main__":
    main()