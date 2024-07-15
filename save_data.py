import pandas as pd
import numpy as np

# Generate a date range
dates = pd.date_range(start='2022-01-01', end='2023-01-01', freq='B')  # 'B' indicates business days

# Create a DataFrame with random data
data = pd.DataFrame(index=dates)
data['Open'] = np.random.uniform(100, 200, size=len(dates))  # Random open prices between 100 and 200
data['High'] = data['Open'] * np.random.uniform(1, 1.05, size=len(dates))  # High is slightly above open
data['Low'] = data['Open'] * np.random.uniform(0.95, 1, size=len(dates))  # Low is slightly below open
data['Close'] = np.random.uniform(data['Low'], data['High'], size=len(dates))  # Close is between low and high
data['Volume'] = np.random.randint(1000, 10000, size=len(dates))  # Random volume between 1000 and 10000

# Save data to PostgreSQL
from sqlalchemy import create_engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost/financial_data')
data.to_sql('historical_data', engine, if_exists='replace', index=True)

# Confirm the data
print(data.head())
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine

# Define the ticker symbol
ticker_symbol = 'AAPL'

# Fetch data from Yahoo Finance
stock_data = yf.download(ticker_symbol, start='2022-01-01', end='2022-01-07')

# Print the fetched data (as you did successfully before)
print(stock_data)

# Define the file path where you want to save the CSV file
csv_file_path = r'C:\Users\faisa\projects\financial-data-platform\stock_data.csv'

# Save the data to a CSV file
stock_data.to_csv(csv_file_path)

# Print confirmation
print(f"Data saved to {csv_file_path}")

# Create a database engine
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost/financial_data')

# Save the DataFrame to the PostgreSQL database
stock_data.to_sql('stock_data', engine, if_exists='replace', index=True)

# Print confirmation
print("Data saved to PostgreSQL database")
