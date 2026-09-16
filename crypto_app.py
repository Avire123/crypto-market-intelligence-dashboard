import json
import os
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title='Crypto Market Tracker', page_icon='🪙', layout='wide')

COIN_ID_MAP = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'XRP': 'ripple',
    'ADA': 'cardano',
    'DOGE': 'dogecoin',
    'BNB': 'binancecoin',
    'AVAX': 'avalanche-2',
    'TRX': 'tron',
    'MATIC': 'matic-network',
    'LINK': 'chainlink',
    'DOT': 'polkadot',
    'LTC': 'litecoin',
    'UNI': 'uniswap',
    'ATOM': 'cosmos',
    'NEAR': 'near',
    'ARB': 'arbitrum',
    'OP': 'optimism',
    'TON': 'the-open-network',
}
WATCHLIST_PATH = 'crypto_watchlist.json'


def parse_numeric_value(value):
    if value is None:
        return 0.0

    cleaned = str(value).replace('$', '').replace(',', '').replace('%', '').strip()
    if not cleaned:
        return 0.0

    multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000, 'T': 1_000_000_000_000}
    last_char = cleaned[-1].upper()
    if last_char in multipliers:
        return float(cleaned[:-1]) * multipliers[last_char]
    return float(cleaned)


@st.cache_data(ttl=300)
def scrape_crypto_data(top_n=20):
    url = 'https://coinmarketcap.com/'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        st.error(f'Could not fetch market data: {error}')
        return pd.DataFrame()

    soup = BeautifulSoup(response.text, 'html.parser')
    crypto_list = []

    for row in soup.select('tbody tr')[:top_n]:
        cols = row.find_all('td')
        if len(cols) < 8:
            continue

        try:
            name_parts = cols[2].find_all('p')
            crypto_list.append(
                {
                    'Name': name_parts[0].get_text(strip=True) if name_parts else 'N/A',
                    'Symbol': name_parts[1].get_text(strip=True) if len(name_parts) > 1 else 'N/A',
                    'Price ($)': parse_numeric_value(cols[3].get_text(strip=True)),
                    '24h Change (%)': parse_numeric_value(cols[5].get_text(strip=True)),
                    'Market Cap ($)': parse_numeric_value(cols[7].get_text(strip=True)),
                }
            )
        except (AttributeError, IndexError, ValueError):
            continue

    return pd.DataFrame(crypto_list)


@st.cache_data(ttl=300)
def fetch_fear_greed_index():
    try:
        response = requests.get(
            'https://api.alternative.me/fng/?limit=1',
            headers={'User-Agent': 'crypto-market-dashboard/1.0'},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        item = payload.get('data', [{}])[0]
        return item.get('value', 'N/A'), item.get('value_classification', 'Unavailable')
    except (requests.RequestException, ValueError, IndexError, AttributeError):
        return 'N/A', 'Unavailable'


def initialize_database(db_path='crypto_history.db'):
    conn = sqlite3.connect(db_path)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            change_24h REAL NOT NULL,
            market_cap REAL NOT NULL
        )
        '''
    )
    conn.commit()
    conn.close()


def save_market_snapshot(df, db_path='crypto_history.db'):
    if df.empty:
        return 0

    records = []
    for _, row in df.iterrows():
        records.append(
            (
                datetime.utcnow().isoformat(),
                str(row['Symbol']).upper(),
                str(row['Name']),
                float(row['Price ($)']),
                float(row['24h Change (%)']),
                float(row['Market Cap ($)']),
            )
        )

    conn = sqlite3.connect(db_path)
    conn.executemany(
        '''
        INSERT INTO market_snapshots (captured_at, symbol, name, price, change_24h, market_cap)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        records,
    )
    conn.commit()
    conn.close()
    return len(records)


def load_historical_data(db_path='crypto_history.db'):
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=['captured_at', 'symbol', 'name', 'price', 'change_24h', 'market_cap'])

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        'SELECT captured_at, symbol, name, price, change_24h, market_cap FROM market_snapshots ORDER BY captured_at ASC',
        conn,
    )
    conn.close()

    if df.empty:
        return df

    df['captured_at'] = pd.to_datetime(df['captured_at'])
    return df.reset_index(drop=True)


def compute_breakout_candidates(history_df):
    if history_df.empty:
        return pd.DataFrame()

    latest = history_df.groupby('symbol', as_index=False).agg(
        latest_price=('price', 'last'),
        avg_price=('price', 'mean'),
        recent_change=('change_24h', 'last'),
    )

    if latest.empty:
        return pd.DataFrame()

    latest['breakout_percent'] = ((latest['latest_price'] / latest['avg_price']) - 1) * 100
    return latest.sort_values('breakout_percent', ascending=False).head(10)


def save_watchlist(symbols):
    with open(WATCHLIST_PATH, 'w', encoding='utf-8') as file:
        json.dump(sorted(set(symbols)), file)


def load_watchlist():
    if not os.path.exists(WATCHLIST_PATH):
        return ['BTC', 'ETH', 'SOL']
    try:
        with open(WATCHLIST_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data if isinstance(data, list) else ['BTC', 'ETH', 'SOL']
    except (json.JSONDecodeError, ValueError):
        return ['BTC', 'ETH', 'SOL']


def send_alert_notification(message, email_to=None, telegram_url=None):
    if email_to:
        try:
            msg = EmailMessage()
            msg['Subject'] = 'Crypto Alert'
            msg['From'] = 'crypto-dashboard@local'
            msg['To'] = email_to
            msg.set_content(message)
            with smtplib.SMTP('localhost') as server:
                server.send_message(msg)
        except Exception:
            pass

    if telegram_url:
        try:
            requests.post(telegram_url, data={'text': message}, timeout=10)
        except requests.RequestException:
            pass


def calculate_sma(values, window):
    return values.rolling(window=window, min_periods=1).mean()


def calculate_ema(values, span):
    return values.ewm(span=span, adjust=False).mean()


def calculate_rsi(values, periods=14):
    delta = values.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / periods, min_periods=periods, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / periods, min_periods=periods, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_bollinger(values, window=20, num_std=2):
    rolling = values.rolling(window=window)
    mid = rolling.mean()
    std = rolling.std()
    upper = mid + std * num_std
    lower = mid - std * num_std
    return mid, upper, lower


@st.cache_data(ttl=300)
def fetch_coin_ohlc(symbol, days=90):
    coin_id = COIN_ID_MAP.get(symbol.upper())
    if not coin_id:
        raise ValueError(f'No OHLC mapping found for {symbol}.')

    url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}'
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    response.raise_for_status()

    payload = response.json()
    if not payload:
        raise ValueError(f'No OHLC data returned for {symbol}.')

    ohlc_df = pd.DataFrame(payload, columns=['Timestamp', 'Open', 'High', 'Low', 'Close'])
    ohlc_df['Date'] = pd.to_datetime(ohlc_df['Timestamp'], unit='ms')
    return ohlc_df[['Date', 'Open', 'High', 'Low', 'Close']]


@st.cache_data(ttl=300)
def fetch_market_correlation(symbols):
    valid_symbols = [symbol for symbol in symbols if symbol.upper() in COIN_ID_MAP]
    if len(valid_symbols) < 2:
        return pd.DataFrame()

    ids = [COIN_ID_MAP[symbol.upper()] for symbol in valid_symbols]
    url = 'https://api.coingecko.com/api/v3/coins/markets?' + 'vs_currency=usd&ids=' + ','.join(ids) + '&sparkline=true'

    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    frames = []
    for item in data:
        symbol = item.get('symbol', '').upper()
        sparkline = item.get('sparkline_in_7d', {}).get('price') or []
        if len(sparkline) < 2:
            continue
        series = pd.Series(sparkline, dtype=float)
        returns = series.pct_change().dropna()
        frames.append(pd.DataFrame({symbol: returns}))

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, axis=1)
    return combined.corr().fillna(1.0)


initialize_database()

with st.sidebar:
    st.header('Dashboard')
    page = st.radio(
        'Navigation',
        ['Overview', 'Portfolio', 'Technical Analysis', 'Historical Data', 'Alerts'],
        index=0,
    )

    st.subheader('Market Controls')
    top_n = st.slider('Number of Cryptocurrencies', min_value=5, max_value=50, value=15, step=5)
    if st.button('Refresh Data', use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.subheader('Watchlist')
    available_symbols = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'BNB', 'AVAX', 'TRX', 'MATIC', 'LINK', 'DOT', 'LTC', 'UNI', 'ATOM']
    saved_watchlist = load_watchlist()
    selected_watchlist = st.multiselect('Saved coins', options=available_symbols, default=saved_watchlist)
    if st.button('Save watchlist', use_container_width=True):
        save_watchlist(selected_watchlist)
        st.toast('Watchlist saved.')

    st.subheader('Paper Portfolio')
    st.caption('One holding per line: SYMBOL, quantity, average cost in USD')
    portfolio_text = st.text_area(
        'Holdings',
        value='BTC, 0.25, 60000\nETH, 2.5, 3000',
        height=120,
    )

    st.subheader('Alerts')
    alert_threshold = st.slider('Alert when 24h drop exceeds (%)', min_value=1.0, max_value=20.0, value=5.0, step=1.0)
    alert_email = st.text_input('Alert email (optional)', value='')
    telegram_webhook = st.text_input('Telegram webhook URL (optional)', value='')
    if st.button('Save current snapshot to database', use_container_width=True):
        snapshot_count = save_market_snapshot(scrape_crypto_data(top_n=top_n))
        st.toast(f'Saved {snapshot_count} rows to the database.')

market_df = scrape_crypto_data(top_n)
if market_df.empty:
    st.warning('No cryptocurrency data is available right now. Try refreshing shortly.')
    st.stop()

market_df['Symbol'] = market_df['Symbol'].str.upper().str.strip()
area_df = market_df.copy()

fear_greed_value, fear_greed_label = fetch_fear_greed_index()

if page == 'Overview':
    st.title('🪙 Real-Time Crypto Market Dashboard')
    st.markdown('Live market data, portfolio simulation, and risk signals in one place.')

    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Total Cryptos Tracked', len(area_df))
    col2.metric(
        'Top Gainer (24h)',
        f"{area_df.loc[area_df['24h Change (%)'].idxmax(), 'Name']} ({area_df.loc[area_df['24h Change (%)'].idxmax(), 'Symbol']})",
        f"{area_df['24h Change (%)'].max():.2f}%",
    )
    col3.metric(
        'Top Loser (24h)',
        f"{area_df.loc[area_df['24h Change (%)'].idxmin(), 'Name']} ({area_df.loc[area_df['24h Change (%)'].idxmin(), 'Symbol']})",
        f"{area_df['24h Change (%)'].min():.2f}%",
    )
    col4.metric('Fear & Greed', fear_greed_label, fear_greed_value)

    st.markdown('---')
    st.subheader('AI Market Summary')
    top_gainer = area_df.loc[area_df['24h Change (%)'].idxmax()]
    top_loser = area_df.loc[area_df['24h Change (%)'].idxmin()]
    summary_text = (
        f"{top_gainer['Symbol']} is leading the market with a {top_gainer['24h Change (%)']:.2f}% move, while "
        f"{top_loser['Symbol']} is underperforming at {top_loser['24h Change (%)']:.2f}%. The market sentiment is "
        f"{fear_greed_label.lower()} with a Fear & Greed score of {fear_greed_value}."
    )
    st.info(summary_text)

    st.subheader('Watchlist')
    if selected_watchlist:
        watchlist_df = area_df[area_df['Symbol'].isin(selected_watchlist)].copy()
        if watchlist_df.empty:
            st.caption('Your watchlist is saved, but none of the selected symbols are visible in the current market table.')
        else:
            st.dataframe(watchlist_df[['Name', 'Symbol', 'Price ($)', '24h Change (%)', 'Market Cap ($)']].round(2), use_container_width=True, hide_index=True)
    else:
        st.caption('Add coins to your watchlist from the sidebar to see live tracking here.')

    st.markdown('---')
    st.subheader('Market Capitalization Comparison')
    market_cap_fig = px.bar(
        area_df,
        x='Symbol',
        y='Market Cap ($)',
        color='Market Cap ($)',
        title='Market Capitalization Comparison',
        template='plotly_dark',
    )
    st.plotly_chart(market_cap_fig, use_container_width=True)

elif page == 'Portfolio':
    st.title('💼 Portfolio Analytics')

    portfolio_rows = []
    for line_number, line in enumerate(portfolio_text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(',')]
        if len(parts) != 3:
            st.warning(f'Holding line {line_number} must have 3 comma-separated values.')
            continue

        symbol, quantity_text, cost_text = parts
        try:
            quantity = float(quantity_text)
            average_cost = float(cost_text)
        except ValueError:
            st.warning(f'Holding line {line_number} contains an invalid number.')
            continue

        match = area_df[area_df['Symbol'] == symbol.upper()]
        if match.empty:
            st.info(f'{symbol.upper()} is not in the scraped top {top_n}.')
            continue

        current_price = float(match.iloc[0]['Price ($)'])
        market_value = quantity * current_price
        invested_value = quantity * average_cost
        portfolio_rows.append(
            {
                'Symbol': symbol.upper(),
                'Quantity': quantity,
                'Average Cost ($)': average_cost,
                'Current Price ($)': current_price,
                'Market Value ($)': market_value,
                'P/L ($)': market_value - invested_value,
                'P/L (%)': ((market_value / invested_value) - 1) * 100 if invested_value else 0,
            }
        )

    if portfolio_rows:
        portfolio_df = pd.DataFrame(portfolio_rows)
        total_value = portfolio_df['Market Value ($)'].sum()
        total_invested = (portfolio_df['Average Cost ($)'] * portfolio_df['Quantity']).sum()
        total_pl = portfolio_df['P/L ($)'].sum()
        portfolio_df['Allocation %'] = (portfolio_df['Market Value ($)'] / total_value * 100) if total_value else 0

        col1, col2, col3 = st.columns(3)
        col1.metric('Portfolio Value', f'${total_value:,.2f}')
        col2.metric('Portfolio P/L', f'${total_pl:,.2f}', f"{((total_pl / total_invested) * 100) if total_invested else 0:.2f}%")
        col3.metric('Invested Capital', f'${total_invested:,.2f}')

        st.subheader('Portfolio Breakdown')
        st.dataframe(portfolio_df.round(2), use_container_width=True, hide_index=True)

        pie_chart = px.pie(
            portfolio_df,
            names='Symbol',
            values='Market Value ($)',
            hole=0.5,
            title='Allocation by Holding',
            template='plotly_dark',
        )
        st.plotly_chart(pie_chart, use_container_width=True)

        best = portfolio_df.loc[portfolio_df['P/L (%)'].idxmax()]
        worst = portfolio_df.loc[portfolio_df['P/L (%)'].idxmin()]
        best_col, worst_col = st.columns(2)
        best_col.metric('Best Performer', f"{best['Symbol']}", f"{best['P/L (%)']:.2f}%")
        worst_col.metric('Worst Performer', f"{worst['Symbol']}", f"{worst['P/L (%)']:.2f}%")
    else:
        st.info('Add at least one valid holding to calculate portfolio metrics.')

elif page == 'Technical Analysis':
    st.title('📉 Technical Analysis')
    selected_symbol = st.selectbox('Select a coin to analyze', options=sorted(area_df['Symbol'].unique().tolist()))

    try:
        ohlc_df = fetch_coin_ohlc(selected_symbol, days=90)
        ohlc_df = ohlc_df.sort_values('Date').reset_index(drop=True)
        ohlc_df['SMA_20'] = calculate_sma(ohlc_df['Close'], 20)
        ohlc_df['SMA_50'] = calculate_sma(ohlc_df['Close'], 50)
        ohlc_df['EMA_20'] = calculate_ema(ohlc_df['Close'], 20)
        ohlc_df['RSI_14'] = calculate_rsi(ohlc_df['Close'], 14)
        mid, upper, lower = calculate_bollinger(ohlc_df['Close'], window=20)
        ohlc_df['BOLLINGER_MID'] = mid
        ohlc_df['BOLLINGER_UPPER'] = upper
        ohlc_df['BOLLINGER_LOWER'] = lower

        candlestick_fig = go.Figure(
            data=[
                go.Candlestick(
                    x=ohlc_df['Date'],
                    open=ohlc_df['Open'],
                    high=ohlc_df['High'],
                    low=ohlc_df['Low'],
                    close=ohlc_df['Close'],
                    name='OHLC',
                )
            ]
        )
        candlestick_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['SMA_20'], mode='lines', name='SMA 20', line=dict(color='#00d9ff', width=2)))
        candlestick_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['SMA_50'], mode='lines', name='SMA 50', line=dict(color='#ffcc00', width=2)))
        candlestick_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['EMA_20'], mode='lines', name='EMA 20', line=dict(color='#8a2be2', width=2)))
        candlestick_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['BOLLINGER_UPPER'], mode='lines', name='Bollinger Upper', line=dict(color='#ff7b72', width=1, dash='dot'), showlegend=False))
        candlestick_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['BOLLINGER_LOWER'], mode='lines', name='Bollinger Lower', line=dict(color='#ff7b72', width=1, dash='dot'), showlegend=False))
        candlestick_fig.update_layout(template='plotly_dark', title=f'{selected_symbol} Candlestick Chart & Trend Indicators', xaxis_title='Date', yaxis_title='Price (USD)', legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1), height=600)
        st.plotly_chart(candlestick_fig, use_container_width=True)

        rsi_fig = go.Figure()
        rsi_fig.add_trace(go.Scatter(x=ohlc_df['Date'], y=ohlc_df['RSI_14'], mode='lines', name='RSI 14'))
        rsi_fig.add_hline(y=70, line_dash='dash', line_color='red')
        rsi_fig.add_hline(y=30, line_dash='dash', line_color='green')
        rsi_fig.update_layout(template='plotly_dark', title=f'{selected_symbol} Relative Strength Index (RSI)', xaxis_title='Date', yaxis_title='RSI', yaxis_range=[0, 100], height=300)
        st.plotly_chart(rsi_fig, use_container_width=True)
    except ValueError:
        st.info(f'OHLC data is not available for {selected_symbol}. Try a major coin like BTC or ETH.')

elif page == 'Historical Data':
    st.title('🗄️ Historical Data')
    historical_df = load_historical_data()
    if historical_df.empty:
        st.info('No historical data is available yet. Save a market snapshot to start tracking history.')
    else:
        history_symbols = sorted(historical_df['symbol'].dropna().unique().tolist())
        history_symbol = st.selectbox('Trend analysis symbol', options=history_symbols)
        history_slice = historical_df[historical_df['symbol'] == history_symbol].sort_values('captured_at')
        if not history_slice.empty:
            history_slice['pct_change'] = history_slice['price'].pct_change().fillna(0)
            history_slice['rolling_volatility'] = history_slice['pct_change'].rolling(window=12, min_periods=2).std().fillna(0) * 100
            trend_fig = px.line(history_slice, x='captured_at', y='price', title=f'{history_symbol} Price History', template='plotly_dark')
            st.plotly_chart(trend_fig, use_container_width=True)
            volatility_fig = px.line(history_slice, x='captured_at', y='rolling_volatility', title=f'{history_symbol} Rolling Volatility (%)', template='plotly_dark')
            st.plotly_chart(volatility_fig, use_container_width=True)

        breakout_df = compute_breakout_candidates(historical_df)
        if not breakout_df.empty:
            st.subheader('Breakout Candidates')
            st.dataframe(breakout_df[['symbol', 'latest_price', 'avg_price', 'breakout_percent', 'recent_change']].round(4), use_container_width=True, hide_index=True)

elif page == 'Alerts':
    st.title('🔔 Alerts & Monitoring')
    triggered_alerts = area_df[area_df['24h Change (%)'] <= -alert_threshold]
    if triggered_alerts.empty:
        st.success(f'No coins are currently below the {alert_threshold:.1f}% alert threshold.')
    else:
        st.warning('Alert triggered for the following symbols:')
        for _, row in triggered_alerts.iterrows():
            st.write(f"- {row['Symbol']}: {row['24h Change (%)']:.2f}% in 24h")

    if alert_email or telegram_webhook:
        alert_summary = ' | '.join(f"{row['Symbol']}: {row['24h Change (%)']:.2f}%" for _, row in triggered_alerts.iterrows())
        if st.button('Send alert test'):
            send_alert_notification(alert_summary, email_to=alert_email or None, telegram_url=telegram_webhook or None)
            st.success('Alert notification sent.')

st.markdown('---')
st.subheader('📊 Market Data')
market_table = area_df[['Name', 'Symbol', 'Price ($)', '24h Change (%)', 'Market Cap ($)']].copy().round(2)
st.dataframe(market_table, use_container_width=True, hide_index=True)

st.markdown('---')
st.subheader('📤 Export')
export_col1, export_col2, export_col3 = st.columns(3)
with export_col1:
    st.download_button('Download CSV', data=area_df.to_csv(index=False).encode('utf-8'), file_name='crypto_market_data.csv', mime='text/csv')
with export_col2:
    st.download_button('Download JSON', data=area_df.to_json(orient='records'), file_name='crypto_market_data.json', mime='application/json')
with export_col3:
    excel_buffer = BytesIO()
    try:
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            area_df.to_excel(writer, index=False, sheet_name='Market Data')
        st.download_button('Download Excel', data=excel_buffer.getvalue(), file_name='crypto_market_data.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception:
        st.caption('Excel export requires openpyxl.')

st.markdown('---')
st.subheader('🔗 Coin Correlation Heatmap')
correlation_symbols = area_df['Symbol'].head(8).tolist()
correlation_df = fetch_market_correlation(correlation_symbols)

if correlation_df.empty:
    st.info('Correlation data is not available for the selected coins right now.')
else:
    corr_fig = px.imshow(
        correlation_df,
        text_auto=True,
        aspect='auto',
        color_continuous_scale='RdYlBu_r',
        title='7-Day Return Correlation Heatmap',
        template='plotly_dark',
    )
    st.plotly_chart(corr_fig, use_container_width=True)
