import logging
import time
import configparser
import yfinance as yf
import psycopg2
from alpaca_trade_api.rest import REST, TimeFrame
from datetime import datetime, timedelta, timezone
import argparse
import math

# Set up logging configuration
log_file_path = 'C:\\Users\\faisa\\Downloads\\trading_script\\real_time_signals.log'
logging.basicConfig(filename=log_file_path, level=logging.INFO, format='%(asctime)s - %(message)s')

# Load Alpaca and PostgreSQL credentials from config
config = configparser.ConfigParser()
config.read('C:\\Users\\faisa\\Downloads\\config.ini')

API_KEY = config.get('Alpaca', 'API_KEY')
API_SECRET = config.get('Alpaca', 'API_SECRET')
BASE_URL = config.get('Alpaca', 'BASE_URL')

DB_NAME = config.get('PostgreSQL', 'DB_NAME')
DB_USER = config.get('PostgreSQL', 'DB_USER')
DB_PASSWORD = config.get('PostgreSQL', 'DB_PASSWORD')
DB_HOST = config.get('PostgreSQL', 'DB_HOST')
DB_PORT = config.get('PostgreSQL', 'DB_PORT')

# Initialize Alpaca API
api = REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Trading Script')
parser.add_argument('--max_positions', type=int, default=None, help='Maximum number of positions')
parser.add_argument('--sort_by', type=str, default=None, help='Sort positions by (max_price, max_high, etc.)')
parser.add_argument('--entry_conditions', type=str, default='moving_average', help='Entry conditions (comma-separated)')
parser.add_argument('--exit_conditions', type=str, default='', help='Exit conditions (comma-separated)')
parser.add_argument('--strategy', type=str, default=None, help='Intraday or daily strategy')
parser.add_argument('--equity_usage', type=float, default=1, help='Percentage of equity to use (0 to 100)')  # Adjusted default to 1%
parser.add_argument('--limit_percent', type=float, default=None, help='Percent from close price for limit order')
args = parser.parse_args()

# Example usage in the script
max_positions = args.max_positions
sort_by = args.sort_by
entry_conditions = args.entry_conditions.split(',') if args.entry_conditions else []
exit_conditions = args.exit_conditions.split(',') if args.exit_conditions else []
strategy = args.strategy
equity_usage = args.equity_usage / 100  # Convert to fraction
limit_percent = args.limit_percent

def save_to_postgres(ticker, signal, price, order_type=None, order_id=None, quantity=None, equity_used=None, trigger_condition=None, error_message=None):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trading_log (ticker, signal, price, order_type, order_id, quantity, equity_used, trigger_condition, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (ticker, signal, float(price), order_type, order_id, quantity, equity_used, trigger_condition, error_message))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f'Error saving to PostgreSQL: {e}')

def detect_signal(data, entry_conditions):
    # Example strategy: Buy if the last price is higher than the moving average
    moving_average = data['moving_average']
    last_price = data['last_price']
    
    if 'moving_average' in entry_conditions:
        if last_price > moving_average:
            logging.info(f'Signal detected for BUY: Last price {last_price} crossed above moving average {moving_average}')
            return 'BUY', f'Last price {last_price} crossed above moving average {moving_average}'
        elif last_price < moving_average:
            logging.info(f'Signal detected for SELL: Last price {last_price} crossed below moving average {moving_average}')
            return 'SELL', f'Last price {last_price} crossed below moving average {moving_average}'
    return None, None

def fetch_historical_data(ticker):
    try:
        # Fetch intraday data from Yahoo Finance
        stock = yf.Ticker(ticker)
        hist = stock.history(interval="1m", period="1d")  # Fetch last 1 day of 1-minute interval data
        last_price = hist['Close'].iloc[-1]
        moving_average = hist['Close'].rolling(window=50).mean().iloc[-1]  # Calculate moving average over last 50 minutes
        
        return {
            'last_price': last_price,
            'moving_average': moving_average
        }
    except Exception as e:
        logging.error(f'Error fetching historical data for {ticker}: {e}')
        return None

def execute_trade(ticker, signal, limit_percent=None):
    try:
        # Check the current position for the ticker
        position = api.get_position(ticker) if ticker in [pos.symbol for pos in api.list_positions()] else None

        # Check the last order for the ticker to avoid wash trades
        last_orders = api.list_orders(status='all', limit=1, symbols=[ticker])
        if last_orders:
            last_order = last_orders[0]
            last_order_side = last_order.side
            last_order_time = last_order.created_at
            time_since_last_order = datetime.now(timezone.utc) - last_order_time

            # Avoid wash trades by checking the time since the last order
            if (signal == 'BUY' and last_order_side == 'sell' and time_since_last_order < timedelta(hours=2)) or \
               (signal == 'SELL' and last_order_side == 'buy' and time_since_last_order < timedelta(hours=2)):
                logging.warning(f'{ticker} - Potential wash trade detected. Skipping order.')
                return

        # Get the current account information
        account = api.get_account()
        buying_power = float(account.buying_power)

        # Get the current market price of the ticker
        bar = api.get_bars(ticker, TimeFrame.Minute, limit=1).df
        current_price = bar['close'].iloc[0]

        # Calculate notional value to trade based on a percentage of buying power
        notional_value = round(buying_power * equity_usage, 2)  # Use the equity usage fraction and round to 2 decimal places

        if signal == 'BUY':
            if limit_percent:
                limit_price = current_price * (1 + limit_percent)
                quantity = math.floor(notional_value / limit_price)  # Round down to the nearest whole number
                if quantity == 0:
                    quantity = 1  # Set minimum quantity to 1 if rounding down results in zero
                order_cost = quantity * limit_price
                if order_cost > buying_power:
                    logging.warning(f'{ticker} - Insufficient funds to place LIMIT BUY order. Required: ${order_cost}, Available: ${buying_power}')
                    save_to_postgres(ticker, 'LIMIT BUY', limit_price, order_type='limit', order_id=None, quantity=quantity, equity_used=equity_usage, error_message='Insufficient funds')
                    return
                order = api.submit_order(
                    symbol=ticker,
                    qty=quantity,
                    side='buy',
                    type='limit',
                    time_in_force='day',
                    limit_price=limit_price
                )
                logging.info(f'{ticker} - Executed LIMIT BUY order at {datetime.now(timezone.utc)}: Ticker {ticker}, Order Type: Limit, Price: {limit_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
                save_to_postgres(ticker, 'LIMIT BUY', limit_price, order_type='limit', order_id=order.id, quantity=quantity, equity_used=equity_usage)
            else:
                quantity = math.floor(notional_value / current_price)  # Round down to the nearest whole number
                if quantity == 0:
                    quantity = 1  # Set minimum quantity to 1 if rounding down results in zero
                order_cost = quantity * current_price
                if order_cost > buying_power:
                    logging.warning(f'{ticker} - Insufficient funds to place MARKET BUY order. Required: ${order_cost}, Available: ${buying_power}')
                    save_to_postgres(ticker, 'MARKET BUY', current_price, order_type='market', order_id=None, quantity=quantity, equity_used=equity_usage, error_message='Insufficient funds')
                    return
                order = api.submit_order(
                    symbol=ticker,
                    qty=quantity,
                    side='buy',
                    type='market',
                    time_in_force='day'
                )
                logging.info(f'{ticker} - Executed MARKET BUY order at {datetime.now(timezone.utc)}: Ticker {ticker}, Order Type: Market, Price: {current_price}, Quantity: {quantity}, Equity Used: {equity_usage * 100}%')
                save_to_postgres(ticker, 'MARKET BUY', current_price, order_type='market', order_id=order.id, quantity=quantity, equity_used=equity_usage)
        elif signal == 'SELL':
            if position and float(position.qty) > 0:
                sell_quantity = min(math.floor(float(position.qty)), 1)  # Ensure sell_quantity does not exceed available position
                if sell_quantity > 0:
                    # Place a sell order if there is a position
                    order = api.submit_order(
                        symbol=ticker,
                        qty=sell_quantity,
                        side='sell',
                        type='market',
                        time_in_force='day'
                    )
                    logging.info(f'{ticker} - Executed SELL order at {datetime.now(timezone.utc)}: Ticker {ticker}, Order Type: Market, Price: {current_price}, Quantity: {sell_quantity}, Equity Used: {equity_usage * 100}%')
                    save_to_postgres(ticker, 'SELL', current_price, order_type='market', order_id=order.id, quantity=sell_quantity, equity_used=equity_usage)
                else:
                    logging.warning(f'{ticker} - Quantity to sell is zero after rounding down. Skipping order.')
            else:
                logging.warning(f'{ticker} - No position or insufficient quantity available for SELL order. Skipping order.')
    except Exception as e:
        if 'insufficient funds' in str(e).lower():
            logging.error(f'Error executing trade for {ticker}: Insufficient funds. Current buying power: ${buying_power}')
            save_to_postgres(ticker, signal, current_price, order_type=None, order_id=None, quantity=None, equity_used=equity_usage, error_message='Insufficient funds')
        else:
            logging.error(f'Error executing trade for {ticker}: {e}')
            save_to_postgres(ticker, signal, current_price, order_type=None, order_id=None, quantity=None, equity_used=equity_usage, error_message=str(e))

def cancel_expired_orders(tickers):
    orders = api.list_orders(status='open')
    for order in orders:
        if order.symbol in tickers and order.type == 'limit':
            order_time = order.created_at
            current_time = datetime.now(timezone.utc)
            time_since_order = current_time - order_time
            if strategy == 'intraday' and time_since_order > timedelta(minutes=15):
                api.cancel_order(order.id)
                logging.info(f'{order.symbol} - Cancelled limit order {order.id} due to exceeding 15-minute timeframe.')
                save_to_postgres(order.symbol, 'CANCEL', None, order_type='limit', order_id=order.id, quantity=None, equity_used=None, error_message='Order cancelled due to 15-minute timeout')
            elif strategy == 'daily' and time_since_order > timedelta(days=1):
                api.cancel_order(order.id)
                logging.info(f'{order.symbol} - Cancelled limit order {order.id} due to exceeding daily timeframe.')
                save_to_postgres(order.symbol, 'CANCEL', None, order_type='limit', order_id=order.id, quantity=None, equity_used=None, error_message='Order cancelled due to daily timeout')

# Call this function periodically
def monitor_real_time(tickers, limit_percent):
    while True:
        cancel_expired_orders(tickers)
        for ticker in tickers:
            logging.info(f'Fetching data for {ticker}')
            data = fetch_historical_data(ticker)
            if data:
                logging.info(f'Data fetched for {ticker}: {data}')
                signal, trigger_condition = detect_signal(data, entry_conditions)
                if signal:
                    logging.info(f'Signal detected for {ticker}: {signal}')
                    execute_trade(ticker, signal, limit_percent)
                else:
                    logging.info(f'No signal detected for {ticker}')
            else:
                logging.info(f'Failed to fetch data for {ticker}')
        time.sleep(60)  # Adjust the interval as needed

if __name__ == "__main__":
    tickers = ['TECL', 'FNGU', 'SOXL', 'GBTC', 'NVDL', 'TSLL']  # Added TECL back to the list
    logging.info('Starting the trading script.')
    monitor_real_time(tickers, limit_percent)