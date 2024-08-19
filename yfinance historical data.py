import yfinance as yf
import pandas as pd
import multiprocessing as mp
from sqlalchemy import create_engine
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Function to calculate technical indicators
def calculate_indicators(df):
    try:
        # Calculate Simple Moving Averages (SMA)
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        
        # Calculate Exponential Moving Averages (EMA)
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # Calculate Relative Strength Index (RSI)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Calculate RSI-2
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs = gain / loss
        df['RSI_2'] = 100 - (100 / (1 + rs))
        
        # Calculate Bollinger Bands
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        df['BB_Upper'] = df['BB_Middle'] + 2 * df['Close'].rolling(window=20).std()
        df['BB_Lower'] = df['BB_Middle'] - 2 * df['Close'].rolling(window=20).std()
        
        # Calculate Bollinger Band ROC (Rate of Change)
        df['bnd_roc7'] = df['BB_Upper'].pct_change(periods=7)
        df['bnd_roc14'] = df['BB_Upper'].pct_change(periods=14)
        df['bnd_roc2'] = df['BB_Upper'].pct_change(periods=2)
        
        # Calculate Internal Bar Strength (IBS)
        df['ibs'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
        
        # Calculate ATR14 (Average True Range)
        df['tr'] = df[['High', 'Close'].shift(1)].max(axis=1) - df[['Low', 'Close'].shift(1)].min(axis=1)
        df['atr14'] = df['tr'].rolling(window=14).mean()
        
        # Identify Bearish Engulfing Pattern
        df['bearish_engulfing'] = (df['Close'].shift(1) < df['Open'].shift(1)) & \
                                  (df['Close'] < df['Open']) & \
                                  (df['Open'] > df['Close'].shift(1)) & \
                                  (df['Close'] > df['Open'].shift(1))
        
        # Identify Bearish Spinning Top Pattern
        body = df['Close'] - df['Open']
        df['bearish_spinning_top'] = (abs(body) < (df['High'] - df['Low']) * 0.3) & \
                                     (body < 0)
        
        logging.info(f"Indicators calculated for {df['ticker'].iloc[0]}")
        return df

    except Exception as e:
        logging.error(f"Error calculating indicators: {e}")
        return df

# Function to fetch and process data for a single ticker
def process_ticker(ticker):
    try:
        # Fetch historical data
        data = yf.download(ticker, start="2004-04-01", end="2024-07-27", interval="1d")
        
        # Check if data is empty
        if data.empty:
            logging.error(f"No data fetched for {ticker}")
            return pd.DataFrame()
        
        # Add a 'ticker' column for reference
        data['ticker'] = ticker
        
        # Calculate indicators
        data = calculate_indicators(data)
        
        # Log the first few rows of the data
        logging.info(f"Data for {ticker}: {data.head()}")
        
        return data
    
    except Exception as e:
        logging.error(f"Error processing data for {ticker}: {e}")
        return pd.DataFrame()

# Function to save DataFrame to PostgreSQL database
def save_to_db(df, db_engine):
    try:
        if not df.empty:
            df.to_sql('historical_data', db_engine, if_exists='append', index=False)
            logging.info(f"Data saved to database for {df['ticker'].iloc[0]}")
        else:
            logging.warning("DataFrame is empty, nothing to save.")
    except Exception as e:
        logging.error(f"Error saving data to database: {e}")

# Main function
def main():
    tickers = ['TECL', 'FNGU', 'SOXL', 'GBTC', 'NVDL', 'TSLL']  # List of tickers to fetch

    # PostgreSQL connection string
    db_engine = create_engine('postgresql://postgres:postgres@localhost:5432/financial_data')

    # Using multiprocessing to fetch data for multiple tickers concurrently
    with mp.Pool(processes=4) as pool:  # Using 'with' to ensure pool is properly closed
        results = pool.map(process_ticker, tickers)
    
    # Log results to check if data is being processed
    for df in results:
        if not df.empty:
            logging.info(f"Processed DataFrame for tickers: {df['ticker'].iloc[0]} - {df.head()}")
    
    # Combine all the dataframes and save to the database
    all_data = pd.concat(results, ignore_index=True)
    if not all_data.empty:
        save_to_db(all_data, db_engine)
    else:
        logging.error("No data available to save to the database")

if __name__ == "__main__":
    main()
