##!/usr/bin/env python3

import logging
import configparser
import yfinance as yf
from datetime import datetime, timedelta
import argparse
import math
import pandas as pd
import os
import quantstats as qs
from functools import lru_cache
import platform

# Ensure the log file exists
log_file_path = 'backtesting_signals.log'
if not os.path.exists(log_file_path):
    with open(log_file_path, 'w') as f:
        pass

# Set up logging configuration
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load general config
config = configparser.ConfigParser()
config.read('config.ini')

# Load date config for cross-platform compatibility
config_dir = os.path.dirname(os.path.abspath(__file__))
dates_ini_path = os.path.join(config_dir, 'dates.ini')
config.read(dates_ini_path)

default_start_date = config.get('Dates', 'start_date')
default_end_date = config.get('Dates', 'end_date')

# Parse command-line arguments for backtesting and live trading
parser = argparse.ArgumentParser(description='Trading Script')
parser.add_argument('--start_date', type=str, default=default_start_date, help='Start date for backtesting (YYYY-MM-DD)')
parser.add_argument('--end_date', type=str, default=default_end_date, help='End date for backtesting (YYYY-MM-DD)')
parser.add_argument('--max_positions', type=int, default=1, help='Maximum number of positions')
parser.add_argument('--sort_by', type=str, default=None, help='Sort positions by (max_price, max_high, etc.)')
parser.add_argument('--entry_conditions', type=str, default='moving_average', help='Entry conditions (comma-separated)')
parser.add_argument('--exit_conditions', type=str, default='', help='Exit conditions (comma-separated)')
parser.add_argument('--strategy', type=str, default=None, help='Intraday or daily strategy')
parser.add_argument('--equity_usage', type=float, default=1, help='Percentage of equity to use (0 to 100)')
parser.add_argument('--limit_percent', type=float, default=None, help='Percent from close price for limit order')
parser.add_argument('--order_type', type=str, choices=['market', 'limit'], default='market', help='Order type: market or limit')
parser.add_argument('--mode', type=str, choices=['backtest', 'livetrade', 'simtrade'], default='backtest', help='Mode: backtest, livetrade, or simtrade')
args = parser.parse_args()

start_date = args.start_date
end_date = args.end_date
max_positions = args.max_positions
sort_by = args.sort_by
entry_conditions = args.entry_conditions.split(',') if args.entry_conditions else []
exit_conditions = args.exit_conditions.split(',') if args.exit_conditions else []
strategy = args.strategy
equity_usage = args.equity_usage / 100
limit_percent = args.limit_percent
order_type = args.order_type
mode = args.mode

@lru_cache(maxsize=32)
def fetch_historical_data(ticker, start_date, end_date):
    try:
        historical_data = yf.download(ticker, start=start_date, end=end_date, interval="1d")
        if historical_data.empty:
            logging.error(f'No historical data available for {ticker} from {start_date} to {end_date}')
            return None
        historical_data['moving_average'] = calculate_sma(historical_data, 20)
        historical_data['atr'] = calculate_atr(historical_data, 14)
        historical_data['natr'] = calculate_natr(historical_data)
        logging.info(f'Fetched historical data for {ticker}: {historical_data.index[-1]}')
        return historical_data
    except Exception as e:
        logging.error(f'Error fetching historical data for {ticker}: {e}')
        return None

def calculate_sma(data, window):
    return data['Close'].rolling(window=window).mean()

def calculate_atr(data, window):
    high_low = data['High'] - data['Low']
    high_close = abs(data['High'] - data['Close'].shift())
    low_close = abs(data['Low'] - data['Close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=window).mean()
    return atr

def calculate_natr(data):
    high = data['High']
    low = data['Low']
    close = data['Close']
    true_range = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = true_range.rolling(window=14).mean()
    natr = (atr / close) * 100

    if natr.isnull().any():
        logging.warning(f'NATR calculation resulted in NaN values. High, Low, Close data might be insufficient.')
        logging.debug(f'High data: {high.tail()}')
        logging.debug(f'Low data: {low.tail()}')
        logging.debug(f'Close data: {close.tail()}')
    
    natr.fillna(0, inplace=True)  # Fill NaNs with 0 to avoid issues

    return natr

def detect_signal(kmlm_data, historical_data):
    kmlm_price = kmlm_data['Close'].iloc[-1]
    kmlm_sma_20 = kmlm_data['moving_average'].iloc[-1]

    if kmlm_price < kmlm_sma_20:
        eligible_tickers = ['TQQQ', 'FNGU', 'SOXL']
        entry_signal = 'price<20SMA'
    else:
        eligible_tickers = ['BIL', 'BTAL', 'SQQQ', 'BITI']
        entry_signal = 'price>20SMA'

    logging.info(f'Eligible Tickers: {eligible_tickers}')

    max_natr_ticker = None
    max_natr_value = -float('inf')

    for ticker in eligible_tickers:
        if ticker in historical_data:
            natr_value = historical_data[ticker]['natr'].iloc[-1]
            if pd.isna(natr_value) or natr_value == 0:
                logging.warning(f'NATR for ticker {ticker} is NaN or 0, skipping.')
                continue
            logging.info(f'Ticker: {ticker}, NATR: {natr_value}')
            if natr_value > max_natr_value:
                max_natr_value = natr_value
                max_natr_ticker = ticker

    if max_natr_ticker:
        logging.info(f'Selected Ticker: {max_natr_ticker}, Entry Signal: {entry_signal}')
        return 'BUY', max_natr_ticker, entry_signal
    else:
        logging.info('No eligible ticker found.')
        return None, None, None

def execute_trade(ticker, signal, current_price, date, trade_log, equity_usage, limit_percent):
    try:
        notional_value = round(100000 * equity_usage, 2)
        quantity = 0

        if signal == 'BUY':
            if limit_percent:
                limit_price = round(current_price * (1 + limit_percent))
                quantity = math.ceil(notional_value / limit_price)
                logging.info(f'{ticker} - Simulated LIMIT BUY order at {date}: Price: {limit_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
            else:
                rounded_price = round(current_price)
                quantity = math.ceil(notional_value / rounded_price)
                logging.info(f'{ticker} - Simulated MARKET BUY order at {date}: Price: {rounded_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
            trade_log.append({"symbol": ticker, "action": "BUY", "price": current_price, "entry_date": date, "shares": quantity})
        elif signal == 'SELL':
            rounded_price = round(current_price)
            sell_quantity = 1
            logging.info(f'{ticker} - Simulated SELL order at {date}: Price: {rounded_price}, Quantity: {sell_quantity}, Equity Used: {equity_usage * 100}%')
            trade_log.append({"symbol": ticker, "action": "SELL", "price": current_price, "exit_date": date, "shares": sell_quantity})
    except Exception as e:
        logging.error(f'Error executing trade for {ticker}: {e}')

class Strategy:
    def __init__(self, start_date, end_date, equity_usage, limit_percent, order_type, mode, max_positions):
        self.start_date = start_date
        self.end_date = end_date
        self.equity_usage = equity_usage
        self.limit_percent = limit_percent
        self.order_type = order_type
        self.mode = mode
        self.max_positions = max_positions
        self.trade_log = []

    def fetch_historical_data(self, ticker):
        return fetch_historical_data(ticker, self.start_date, self.end_date)
   
    def detect_signal(self, kmlm_data, historical_data):
        return detect_signal(kmlm_data, historical_data)

    def execute_trade(self, ticker, signal, current_price, date):
        return execute_trade(ticker, signal, current_price, date, self.trade_log, self.equity_usage, self.limit_percent)

    def log_positions(self, positions):
        for position in positions:
            logging.info(f'Ticker: {position["ticker"]}, Entry Date: {position["entry_date"]}, Entry Price: {position["entry_price"]}')

class BacktestStrategy(Strategy):
    def run(self):
        kmlm_data = self.fetch_historical_data('KMLM')
        if kmlm_data is None:
            logging.error('Failed to fetch KMLM data. Exiting backtest.')
            return

        historical_data = {ticker: self.fetch_historical_data(ticker) for ticker in ['TQQQ', 'FNGU', 'SOXL', 'BTAL', 'BIL', 'SQQQ', 'BITI'] if self.fetch_historical_data(ticker) is not None}

        positions = []
        aggregate_pnl = 0.0
        trade_records = []

        kmlm_dates = kmlm_data.index

        for date in kmlm_dates:
            kmlm_price = kmlm_data.loc[date, 'Close']
            kmlm_sma_20 = kmlm_data.loc[date, 'moving_average']

            # Exit logic
            for position in positions[:]:
                ticker = position['ticker']
                ticker_data = historical_data[ticker]
                if date not in ticker_data.index:
                    continue
                row = ticker_data.loc[date]

                exit_signal, reason = self.check_exit_conditions(kmlm_data, date, row, position)
                if exit_signal:
                    self.execute_trade(ticker, 'SELL', row['Close'], date)
                    pnl = (row['Close'] - position['entry_price']) * position['shares']
                    aggregate_pnl += pnl
                    logging.info(f'PnL for {ticker} at {date}: {pnl}')
                    trade_records.append({
                        "symbol": ticker, "action": "SELL", "exit_signal": reason,
                        "entry_date": position['entry_date'], "entry_price": position['entry_price'],
                        "exit_date": date, "exit_price": row['Close'], "shares": position['shares'], "pnl": pnl
                    })
                    positions.remove(position)

            self.log_positions(positions)

            # Entry logic only if new positions are available
            if len(positions) < self.max_positions:
                signal, max_natr_ticker, entry_signal = self.detect_signal(
                    kmlm_data.loc[:date],
                    {ticker: df.loc[:date] for ticker, df in historical_data.items()}
                )
                if signal and max_natr_ticker:
                    row = historical_data[max_natr_ticker].loc[date]
                    self.execute_trade(max_natr_ticker, 'BUY', row['Close'], date)
                    positions.append({
                        "entry_date": date, "entry_price": row['Close'],
                        "shares": 1, "entry_signal": entry_signal, "ticker": max_natr_ticker
                    })
                    trade_records.append({
                        "symbol": max_natr_ticker, "action": "BUY",
                        "entry_signal": entry_signal, "entry_date": date,
                        "entry_price": row['Close'], "shares": 1
                    })

        logging.info(f'Aggregate PnL from {self.start_date} to {self.end_date}: {aggregate_pnl}')
        self.generate_report(trade_records)

    def check_exit_conditions(self, kmlm_data, date, row, position):
        if position is None or 'ticker' not in position:
            return False, None
        kmlm_price = kmlm_data.loc[date]['Close']
        kmlm_sma_20 = kmlm_data.loc[date]['moving_average']
        current_price = row['Close']
        entry_price = position['entry_price']
        ticker = position['ticker']

        exit_conditions = [
            (kmlm_price > kmlm_sma_20) and (ticker in ['TQQQ', 'FNGU', 'SOXL']),
            (kmlm_price < kmlm_sma_20) and (ticker in ['BIL', 'BTAL', 'SQQQ', 'BITI']),
            (current_price >= entry_price + 3 * row['atr']),
            (current_price >= entry_price * 1.05),
            (date >= position['entry_date'] + timedelta(days=5))
        ]

        for i, condition in enumerate(exit_conditions):
            if condition:
                return True, f"Condition {i+1}"

        return False, None

    def generate_report(self, trades_log):
        trades_log_df = pd.DataFrame(trades_log)
        trades_log_df.to_csv('trades_log.csv', index=False)

        trades_log_df['date'] = pd.to_datetime(trades_log_df.apply(
            lambda row: row['exit_date'] if pd.notna(row['exit_date']) else row['entry_date'], axis=1
        ))
        trades_log_df.set_index('date', inplace=True)

        trades_log_df['returns'] = trades_log_df['pnl'] / trades_log_df['entry_price'].abs()
        returns = trades_log_df['returns'].dropna()
        qs.reports.html(returns, output='report.html')
        logging.info('QuantStats report generated.')

if __name__ == "__main__":
    tickers = ['TQQQ', 'FNGU', 'SOXL', 'BTAL', 'BIL', 'SQQQ', 'BITI']

    logging.info(f'Script started on Python {platform.python_version()}.')

    if mode == 'backtest':
        strategy = BacktestStrategy(start_date, end_date, equity_usage, limit_percent, order_type, mode, max_positions)
        strategy.run()
    elif mode == 'livetrade':
        pass  # Implement live trading logic here
    elif mode == 'simtrade':
        pass  # Implement simulation trading logic here

    logging.info('Script completed successfully.')
