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
    
    # Calculate the end date for the historical data request (now)
    end_date = pd.Timestamp.now()
    
    # Calculate the start date (5 months ago)
    start_date = end_date - pd.DateOffset(months=5)
    
    # Request historical data
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_date,
        durationStr='5 M',  # Request 5 months of historical data
        barSizeSetting='5 mins',
        whatToShow='TRADES',
        useRTH=True
    )
    
    ib.disconnect()
    
    df = pd.DataFrame(bars)
    return df

def main():
    symbols = ['AAPL', 'MSFT', 'GOOGL']  # Example list of symbols
    for symbol in symbols:
        df = fetch_historical_data_ibkr(symbol)
        save_to_postgresql(df, 'ohlcv', 'financial_data', 'postgres', 'postgres', 'localhost')

if __name__ == "__main__":
    main()
