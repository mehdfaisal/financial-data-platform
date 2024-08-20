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
    pip install yfinance pandas ta-lib SQLAlchemy alpaca-trade-api argparse quantstats ipython pyarrow psycopg2 selenium
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

5. ## Fixing QuantStats `numpy.product` Error

If you encounter an `AttributeError` due to `numpy.product` when using QuantStats, follow these steps to resolve it:

i. **Locate the `stats.py` file:**
   - Navigate to the QuantStats installation directory, which is typically located within your Python environment's site-packages directory. The path might look something like this:
     ```
     C:\Users\<YourUsername>\AppData\Local\Programs\Python\Python312\Lib\site-packages\quantstats
     ```
   - Replace `<YourUsername>` with your actual Windows username.

ii. **Edit the `stats.py` file:**
   - Open `stats.py` with a text editor.
   - Search for the line containing `numpy.product`.
   - Replace `numpy.product` with `numpy.prod`:
     ```python
     return _np.prod(1 + returns) ** (1 / len(returns)) - 1
     ```

iii. **Save the changes:**
   - Save the file and close the text editor.

iv. **Alternative: Update QuantStats:**
   - Consider updating QuantStats to the latest version using pip:
     ```sh
     pip install --upgrade quantstats
     ```
