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

### 5. Backtesting Script
