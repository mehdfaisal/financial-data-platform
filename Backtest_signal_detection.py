import logging
import time
import configparser
import yfinance as yf
import psycopg2
from datetime import datetime, timedelta, timezone
import argparse
import math
import pandas as pd

# Set up logging configuration
log_file_path = 'C:\\Users\\faisa\\Downloads\\trading_script\\backtesting_signals.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load general config
config = configparser.ConfigParser()
config.read('C:\\Users\\faisa\\Downloads\\config.ini')

DB_NAME = config.get('PostgreSQL', 'DB_NAME')
DB_USER = config.get('PostgreSQL', 'DB_USER')
DB_PASSWORD = config.get('PostgreSQL', 'DB_PASSWORD')
DB_HOST = config.get('PostgreSQL', 'DB_HOST')
DB_PORT = config.get('PostgreSQL', 'DB_PORT')

# Load date config
config.read('C:\\Users\\faisa\\projects\\financial-data-platform\\dates.ini')
default_start_date = config.get('Dates', 'start_date')
default_end_date = config.get('Dates', 'end_date')

# Parse command-line arguments for backtesting
parser = argparse.ArgumentParser(description='Backtesting Script')
parser.add_argument('--start_date', type=str, default=default_start_date, help='Start date for backtesting (YYYY-MM-DD)')
parser.add_argument('--end_date', type=str, default=default_end_date, help='End date for backtesting (YYYY-MM-DD)')
parser.add_argument('--max_positions', type=int, default=None, help='Maximum number of positions')
parser.add_argument('--sort_by', type=str, default=None, help='Sort positions by (max_price, max_high, etc.)')
parser.add_argument('--entry_conditions', type=str, default='moving_average', help='Entry conditions (comma-separated)')
parser.add_argument('--exit_conditions', type=str, default='', help='Exit conditions (comma-separated)')
parser.add_argument('--strategy', type=str, default=None, help='Intraday or daily strategy')
parser.add_argument('--equity_usage', type=float, default=1, help='Percentage of equity to use (0 to 100)')
parser.add_argument('--limit_percent', type=float, default=None, help='Percent from close price for limit order')
args = parser.parse_args()

# Variables
start_date = args.start_date
end_date = args.end_date
max_positions = args.max_positions
sort_by = args.sort_by
entry_conditions = args.entry_conditions.split(',') if args.entry_conditions else []
exit_conditions = args.exit_conditions.split(',') if args.exit_conditions else []
strategy = args.strategy
equity_usage = args.equity_usage / 100
limit_percent = args.limit_percent

def adjust_date_range(start_date, end_date):
    current_date = datetime.now()
    logging.info(f'Current date: {current_date}')
    if (current_date - datetime.strptime(start_date, '%Y-%m-%d')).days > 30:
        start_date = (current_date - timedelta(days=30)).strftime('%Y-%m-%d')
        logging.info(f'Adjusted start_date to be within the last 30 days: {start_date}')
    if (current_date - datetime.strptime(end_date, '%Y-%m-%d')).days > 30:
        end_date = current_date.strftime('%Y-%m-%d')
        logging.info(f'Adjusted end_date to be within the same day: {end_date}')
    if datetime.strptime(end_date, '%Y-%m-%d') > current_date:
        end_date = current_date.strftime('%Y-%m-%d')
        logging.info(f'Adjusted end_date since it was in the future: {end_date}')
    return start_date, end_date

start_date, end_date = adjust_date_range(start_date, end_date)

def save_to_postgres(ticker, signal, price, event_time, order_type=None, order_id=None, quantity=None, equity_used=None, trigger_condition=None, error_message=None):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        if not isinstance(event_time, datetime):
            event_time = pd.to_datetime(event_time)
        event_time_str = event_time.strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO trading_log (ticker, signal, price, event_time, order_type, order_id, quantity, equity_used, trigger_condition, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (ticker, signal, round(float(price)), event_time_str, order_type, order_id, quantity, equity_used, trigger_condition, error_message))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f'Error saving to PostgreSQL: {e}')

def save_intraday_data_to_postgres(ticker, historical_data):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        for timestamp, row in historical_data.iterrows():
            if not isinstance(timestamp, datetime):
                timestamp = pd.to_datetime(timestamp)
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                INSERT INTO intraday_data (ticker, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (ticker, timestamp_str, round(row['Open']), round(row['High']), round(row['Low']), round(row['Close']), round(row['Volume'])))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f'Error saving intraday data for {ticker} to PostgreSQL: {e}')

def calculate_sma(data, window):
    return data['Close'].rolling(window=window).mean()

def calculate_atr(data, window):
    high_low = data['High'] - data['Low']
    high_close = abs(data['High'] - data['Close'].shift())
    low_close = abs(data['Low'] - data['Close'].shift())
    ranges = high_low.to_frame('hl').join(high_close.to_frame('hc')).join(low_close.to_frame('lc'))
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(window=window).mean()
    return atr

def calculate_natr(data):
    high = data['High']
    low = data['Low']
    close = data['Close']
    tr = pd.DataFrame()
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    tr['tr'] = tr[['h-l', 'h-pc', 'l-pc']].max(axis=1)
    atr = tr['tr'].rolling(window=14).mean()
    natr = (atr / close) * 100
    return natr

def check_kmlm_condition(kmlm_data, condition_days=20):
    kmlm_data['SMA_20'] = kmlm_data['Close'].rolling(window=condition_days).mean()
    last_price = kmlm_data['Close'].iloc[-1]
    sma_20 = kmlm_data['SMA_20'].iloc[-1]
    return last_price >= sma_20, last_price < sma_20

def detect_signal(kmlm_data, historical_data, entry_conditions):
    kmlm_price = kmlm_data['Close'].iloc[-1]
    kmlm_sma_20 = kmlm_data['SMA_20'].iloc[-1]

    if kmlm_price < kmlm_sma_20:
        eligible_tickers = ['TQQQ', 'FNGU', 'SOXL']
        logging.info(f'KMLM price {kmlm_price} is below SMA 20 {kmlm_sma_20}. Eligible tickers: {eligible_tickers}')
    elif kmlm_price > kmlm_sma_20:
        eligible_tickers = ['BIL', 'BTAL', 'SQQQ', 'BITI']
        logging.info(f'KMLM price {kmlm_price} is above SMA 20 {kmlm_sma_20}. Eligible tickers: {eligible_tickers}')

    max_natr_ticker = None
    max_natr_value = -float('inf')

    for ticker in eligible_tickers:
        if ticker in historical_data:
            natr_value = historical_data[ticker]['natr'].iloc[-1]
            logging.info(f'Checking NATR for {ticker}: {natr_value}')
            if natr_value > max_natr_value:
                max_natr_value = natr_value
                max_natr_ticker = ticker

    if max_natr_ticker:
        logging.info(f'Selected {max_natr_ticker} with highest NATR {max_natr_value}')
        return 'BUY', max_natr_ticker
    else:
        logging.info('No eligible ticker found')
        return None, None

def fetch_historical_data(ticker, start_date, end_date):
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        delta = timedelta(days=7)
        historical_data = pd.DataFrame()

        logging.info(f'Fetching historical data for {ticker} from {start_date} to {end_date}')
        while start_date < end_date:
            chunk_end_date = min(start_date + delta, end_date)
            logging.info(f'Fetching chunk from {start_date} to {chunk_end_date}')
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=chunk_end_date, interval="1d")  # Adjusted to 1-day interval
            if not hist.empty:
                hist = hist.reset_index()  # Reset the index to ensure unique indices
                historical_data = pd.concat([historical_data, hist], ignore_index=True)
            start_date += delta

        if historical_data.empty:
            logging.error(f'No historical data available for {ticker} from {start_date} to {end_date}')
            return None

        historical_data['moving_average'] = calculate_sma(historical_data, 20)
        historical_data['atr'] = calculate_atr(historical_data, 14)
        historical_data['natr'] = calculate_natr(historical_data)  # NATR calculation
        save_intraday_data_to_postgres(ticker, historical_data)
        logging.info(f'Fetched historical data for {ticker}: {historical_data.iloc[-1]}')
        return historical_data
    except Exception as e:
        logging.error(f'Error fetching historical data for {ticker}: {e}')
        return None

def execute_trade(ticker, signal, current_price, event_time, limit_percent=None):
    try:
        notional_value = round(100000 * equity_usage, 2)
        quantity = 0

        if signal == 'BUY':
            if limit_percent:
                limit_price = round(current_price * (1 + limit_percent))
                quantity = math.ceil(notional_value / limit_price)
                logging.info(f'{ticker} - Simulated LIMIT BUY order at {event_time}: Price: {limit_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
                save_to_postgres(ticker, 'LIMIT BUY', limit_price, event_time, order_type='limit', quantity=quantity, equity_used=equity_usage)
            else:
                rounded_price = round(current_price)
                quantity = math.ceil(notional_value / rounded_price)
                logging.info(f'{ticker} - Simulated MARKET BUY order at {event_time}: Price: {rounded_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
                save_to_postgres(ticker, 'MARKET BUY', rounded_price, event_time, order_type='market', quantity=quantity, equity_used=equity_usage)
        elif signal == 'SELL':
            rounded_price = round(current_price)
            sell_quantity = 1
            logging.info(f'{ticker} - Simulated SELL order at {event_time}: Price: {rounded_price}, Quantity: {sell_quantity}, Equity Used: {equity_usage * 100}%')
            save_to_postgres(ticker, 'SELL', rounded_price, event_time, order_type='market', quantity=sell_quantity, equity_used=equity_usage)
    except Exception as e:
        logging.error(f'Error executing trade for {ticker}: {e}')
        save_to_postgres(ticker, signal, current_price, event_time, order_type=None, quantity=None, equity_used=equity_usage, error_message=str(e))

def handle_exit_conditions(trade_record, historical_data, kmlm_data, exit_conditions):
    trade_date = trade_record['event_time']
    trade_ticker = trade_record['ticker']
    trade_price = trade_record['price']
    trade_atr = trade_record['atr']

    current_date = datetime.now()
    current_price = historical_data[trade_ticker]['Close'].iloc[-1]
    kmlm_price = kmlm_data['Close'].iloc[-1]
    kmlm_sma_20 = kmlm_data['SMA_20'].iloc[-1]

    if 'price@kmlm>sma(20)@kmlm' in exit_conditions and kmlm_price > kmlm_sma_20 and trade_ticker in ['TQQQ', 'FNGU', 'SOXL']:
        logging.info(f'Exit condition met: KMLM price {kmlm_price} is above SMA 20 {kmlm_sma_20} for {trade_ticker}')
        return True
    elif 'price@kmlm<sma(20)@kmlm' in exit_conditions and kmlm_price < kmlm_sma_20 and trade_ticker in ['BIL', 'BTAL', 'SQQQ', 'BITI']:
        logging.info(f'Exit condition met: KMLM price {kmlm_price} is below SMA 20 {kmlm_sma_20} for {trade_ticker}')
        return True
    elif 'Current price>Entry price + 3*14 day ATR' in exit_conditions and current_price > trade_price + 3 * trade_atr:
        logging.info(f'Exit condition met: Current price {current_price} is above entry price {trade_price} + 3 * ATR {trade_atr}')
        return True
    elif 'Current price>Entry price*1.05' in exit_conditions and current_price > trade_price * 1.05:
        logging.info(f'Exit condition met: Current price {current_price} is above entry price {trade_price} * 1.05')
        return True
    elif '5 days since entry' in exit_conditions and (current_date - trade_date).days >= 5:
        logging.info(f'Exit condition met: 5 days since entry for {trade_ticker}')
        return True

    return False

def backtest(tickers, start_date, end_date, limit_percent):
    kmlm_data = fetch_historical_data('KMLM', start_date, end_date)
    if kmlm_data is None:
        logging.error('Failed to fetch KMLM data. Exiting backtest.')
        return

    kmlm_above_sma, kmlm_below_sma = check_kmlm_condition(kmlm_data)

    eligible_tickers_above_sma = ['TQQQ', 'FNGU', 'SOXL']
    eligible_tickers_below_sma = ['BIL', 'BTAL', 'SQQQ', 'BITI']

    historical_data = {ticker: fetch_historical_data(ticker, start_date, end_date) for ticker in tickers if fetch_historical_data(ticker, start_date, end_date) is not None}

    # Evaluate entry conditions and find the stock with the highest NATR
    signal, max_natr_ticker = detect_signal(kmlm_data, historical_data, entry_conditions)

    if signal:
        logging.info(f'Signal detected for {max_natr_ticker}: {signal}')
        max_natr_data = historical_data[max_natr_ticker]
        position = 0
        aggregate_pnl = 0.0

        for index, row in max_natr_data.iterrows():
            logging.info(f'Processing data for {max_natr_ticker} at {index}')
            data = {
                'last_price': row['Close'],
                'moving_average': row['moving_average'],
                'atr': row['atr'],
                'natr': row['natr']
            }
            signal, trigger_condition = detect_signal(kmlm_data, historical_data, entry_conditions)
            if signal:
                logging.info(f'Signal detected for {max_natr_ticker}: {signal} at {index}')
                execute_trade(max_natr_ticker, signal, data['last_price'], index, limit_percent)
                # Update position
                if signal == 'BUY':
                    position += math.ceil(row['Close'])
                elif signal == 'SELL':
                    pnl = math.ceil(position - row['Close'])
                    position = 0
                    aggregate_pnl += pnl
                    logging.info(f'PnL for {max_natr_ticker} at {index}: {pnl}')
            else:
                logging.info(f'No signal detected for {max_natr_ticker} at {index}')

        logging.info(f'Aggregate PnL for {max_natr_ticker} from {start_date} to {end_date}: {math.ceil(aggregate_pnl)}')

if __name__ == "__main__":
    tickers = ['TQQQ', 'FNGU', 'SOXL', 'BTAL', 'BIL', 'SQQQ', 'BITI']
    logging.info('Starting the backtesting script.')
    backtest(tickers, start_date, end_date, limit_percent)