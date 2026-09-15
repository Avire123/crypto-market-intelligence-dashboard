import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.express as px


st.set_page_config(
    page_title="Crypto Market Tracker",
    page_icon="🪙",
    layout="wide",
)


def parse_numeric_value(value):
    """Convert values such as '$2.5B', '4.2%' and '12,345' to floats."""
    cleaned = str(value).replace("$", "").replace(",", "").replace("%", "").strip()

    if not cleaned:
        return 0.0

    multipliers = {
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "T": 1_000_000_000_000,
    }

    suffix = cleaned[-1].upper()
    if suffix in multipliers:
        number = cleaned[:-1]
        return float(number) * multipliers[suffix]

    return float(cleaned)


@st.cache_data(ttl=300)
def scrape_crypto_data(top_n=20):
    """Scrape top cryptocurrency metrics from CoinMarketCap."""
    url = "https://coinmarketcap.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Failed to fetch cryptocurrency data: {exc}")
        return pd.DataFrame()

    soup = BeautifulSoup(response.text, "html.parser")
    table_rows = soup.select("tbody tr")[:top_n]

    crypto_list = []

    for row in table_rows:
        cols = row.find_all("td")

        if len(cols) < 8:
            continue

        try:
            name_p = cols[2].find_all("p")
            name = name_p[0].text.strip() if name_p else "N/A"
            symbol = name_p[1].text.strip() if len(name_p) > 1 else "N/A"

            crypto_list.append(
                {
                    "Name": name,
                    "Symbol": symbol,
                    "Price ($)": parse_numeric_value(cols[3].text),
                    "24h Change (%)": parse_numeric_value(cols[5].text),
                    "Market Cap ($)": parse_numeric_value(cols[7].text),
                }
            )
        except (AttributeError, ValueError, IndexError):
            continue

    return pd.DataFrame(crypto_list)


@st.cache_data(ttl=300)
def fetch_fear_greed_index():
    """Fetch the current Crypto Fear & Greed Index."""
    try:
        response = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": "crypto-market-dashboard/1.0"},
            timeout=15,
        )
        response.raise_for_status()

        payload = response.json()
        item = payload.get("data", [{}])[0]

        return (
            item.get("value", "N/A"),
            item.get("value_classification", "Unavailable"),
        )
    except (requests.RequestException, ValueError, IndexError, AttributeError):
        return "N/A", "Unavailable"


def build_portfolio_dataframe(portfolio_text, market_df):
    """Convert paper portfolio input into a portfolio DataFrame."""
    portfolio_rows = []

    for line_number, line in enumerate(portfolio_text.splitlines(), start=1):
        if not line.strip():
            continue

        parts = [part.strip() for part in line.split(",")]

        if len(parts) != 3:
            st.sidebar.warning(
                f"Holding line {line_number} must have 3 comma-separated values."
            )
            continue

        symbol, quantity_text, cost_text = parts

        try:
            quantity = float(quantity_text)
            average_cost = float(cost_text)
        except ValueError:
            st.sidebar.warning(
                f"Holding line {line_number} contains an invalid number."
            )
            continue

        if quantity < 0 or average_cost < 0:
            st.sidebar.warning(
                f"Holding line {line_number} cannot contain negative values."
            )
            continue

        match = market_df[market_df["Symbol"] == symbol.upper()]

        if match.empty:
            st.sidebar.info(
                f"{symbol.upper()} is not in the scraped top {len(market_df)}."
            )
            continue

        current_price = match.iloc[0]["Price ($)"]
        market_value = quantity * current_price
        invested_value = quantity * average_cost

        portfolio_rows.append(
            {
                "Symbol": symbol.upper(),
                "Quantity": quantity,
                "Average Cost ($)": average_cost,
                "Current Price ($)": current_price,
                "Market Value ($)": market_value,
                "P/L ($)": market_value - invested_value,
                "P/L (%)": (
                    ((market_value / invested_value) - 1) * 100
                    if invested_value
                    else 0
                ),
            }
        )

    return pd.DataFrame(portfolio_rows)


# Dashboard Header
st.title("🪙 Real-Time Crypto Market Dashboard")
st.markdown(
    "Live market data, portfolio simulation, and risk signals in one place."
)

# Sidebar controls
st.sidebar.header("Dashboard Controls")
num_coins = st.sidebar.slider(
    "Number of Cryptocurrencies",
    min_value=5,
    max_value=50,
    value=15,
    step=5,
)

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.subheader("Paper Portfolio")
st.sidebar.caption("One holding per line: SYMBOL, quantity, average cost in USD")

portfolio_text = st.sidebar.text_area(
    "Holdings",
    value="BTC, 0.25, 60000\nETH, 2.5, 3000",
    height=100,
)

# Main application logic
df = scrape_crypto_data(top_n=num_coins)

if not df.empty:
    df["Symbol"] = df["Symbol"].str.upper().str.strip()

    top_gainer = df.loc[df["24h Change (%)"].idxmax()]
    top_loser = df.loc[df["24h Change (%)"].idxmin()]
    fear_greed_value, fear_greed_label = fetch_fear_greed_index()

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Cryptos Tracked", len(df))

    col2.metric(
        "Top Gainer (24h)",
        f"{top_gainer['Name']} ({top_gainer['Symbol']})",
        f"{top_gainer['24h Change (%)']:.2f}%",
    )

    col3.metric(
        "Top Loser (24h)",
        f"{top_loser['Name']} ({top_loser['Symbol']})",
        f"{top_loser['24h Change (%)']:.2f}%",
    )

    col4.metric("Fear & Greed", fear_greed_label, fear_greed_value)

    # Paper portfolio
    portfolio_df = build_portfolio_dataframe(portfolio_text, df)

    if not portfolio_df.empty:
        total_value = portfolio_df["Market Value ($)"].sum()
        total_invested = (
            portfolio_df["Average Cost ($)"] * portfolio_df["Quantity"]
        ).sum()
        total_pl = portfolio_df["P/L ($)"].sum()

        portfolio_col1, portfolio_col2, portfolio_col3 = st.columns(3)

        portfolio_col1.metric("Portfolio Value", f"${total_value:,.2f}")
        portfolio_col2.metric(
            "Portfolio P/L",
            f"${total_pl:,.2f}",
            f"{(total_pl / total_invested * 100) if total_invested else 0:.2f}%",
        )
        portfolio_col3.metric("Invested Capital", f"${total_invested:,.2f}")

        allocation_col, table_col = st.columns([1, 2])

        with allocation_col:
            allocation_fig = px.pie(
                portfolio_df,
                names="Symbol",
                values="Market Value ($)",
                hole=0.55,
                title="Portfolio Allocation",
                template="plotly_dark",
            )
            st.plotly_chart(allocation_fig, width="stretch")

        with table_col:
            st.subheader("Paper Portfolio")
            st.dataframe(
                portfolio_df,
                width="stretch",
                hide_index=True,
            )

    # Download
    st.download_button(
        "Download Market Data (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="crypto_market_data.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("📊 Scraped Market Data")
    st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("📈 Exploratory Data Analysis")

    viz_col1, viz_col2 = st.columns(2)

    with viz_col1:
        fig_mc = px.bar(
            df,
            x="Symbol",
            y="Market Cap ($)",
            color="Market Cap ($)",
            title="Market Capitalization Comparison",
            labels={"Market Cap ($)": "Market Cap (USD)"},
            template="plotly_dark",
        )
        st.plotly_chart(fig_mc, width="stretch")

    with viz_col2:
        fig_change = px.bar(
            df,
            x="Symbol",
            y="24h Change (%)",
            color="24h Change (%)",
            color_continuous_scale=["red", "gray", "green"],
            title="24-Hour Price Change (%)",
            template="plotly_dark",
        )
        st.plotly_chart(fig_change, width="stretch")

else:
    st.warning("No data retrieved. Click 'Refresh Data' or try again later.")
