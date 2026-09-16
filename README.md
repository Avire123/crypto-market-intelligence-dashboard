# 🪙 Crypto Market Intelligence Dashboard

> A real-time cryptocurrency market monitoring application built with Python, web scraping, Pandas, Plotly, and Streamlit.

## Overview

This project is an end-to-end data engineering and analytics application that scrapes cryptocurrency market data from CoinMarketCap, processes it with Pandas, and presents the results through an interactive Streamlit dashboard.

The dashboard combines live market metrics, market-movement indicators, crypto sentiment, exploratory visualizations, and a paper portfolio simulator.

## Key Features

- **Automated web scraping** of cryptocurrency market data using `Requests` and `BeautifulSoup`
- Tracks:
  - Cryptocurrency name
  - Symbol
  - Price (USD)
  - 24-hour percentage change
  - Market capitalization
- **Top gainer and top loser** identification based on 24-hour price movement
- **Crypto Fear & Greed Index** integration through the Alternative.me API
- **Paper portfolio simulator** with:
  - Quantity
  - Average purchase cost
  - Current market value
  - Profit/loss in USD
  - Profit/loss percentage
  - Portfolio allocation
- **Interactive Plotly visualizations**
- **CSV export** of scraped market data
- Adjustable tracking range from **5 to 50 cryptocurrencies**
- Five-minute data caching to reduce unnecessary requests

## Dashboard Preview

<img width="1354" height="685" alt="dashboard" src="https://github.com/user-attachments/assets/f3079e59-36fc-4759-b557-65e400707e86" />
<img width="1279" height="969" alt="2" src="https://github.com/user-attachments/assets/90df8c53-f238-426b-a1f6-9f5aaab573dc" />
<img width="1279" height="969" alt="3" src="https://github.com/user-attachments/assets/c7c181ae-fa3a-4b2a-b94a-6430247fe88b" />
<img width="1279" height="956" alt="4" src="https://github.com/user-attachments/assets/98362c27-7d9c-4216-9014-98deac77acf2" />

## Project Structure

```text
crypto-market-intelligence-dashboard/
│
├── app.py                  # Streamlit dashboard application
├── crypto.ipynb            # Original development notebook
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
├── .gitignore              # Git exclusions
├── LICENSE                 # MIT license
└── screenshots/
    └── dashboard.png       # Optional dashboard screenshot
```

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Application and data processing |
| Requests | HTTP requests |
| BeautifulSoup4 | HTML parsing and web scraping |
| Pandas | Data manipulation |
| Plotly Express | Interactive visualization |
| Streamlit | Dashboard and web application |

## Data Sources

### CoinMarketCap

The application retrieves cryptocurrency market information from the public CoinMarketCap website.

The scraper currently reads table rows from the site's HTML structure. Because website layouts can change, the scraper may require maintenance if CoinMarketCap changes its page structure.

### Alternative.me

The dashboard retrieves the Crypto Fear & Greed Index through the Alternative.me API.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/crypto-market-intelligence-dashboard.git
cd crypto-market-intelligence-dashboard
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the dashboard

```bash
streamlit run app.py
```

The application will open in your browser.

## Using the Paper Portfolio

Enter one holding per line using:

```text
SYMBOL, quantity, average cost in USD
```

Example:

```text
BTC, 0.25, 60000
ETH, 2.5, 3000
```

The dashboard then calculates the current market value and paper profit/loss using the latest scraped price.

## Example Workflow

```text
CoinMarketCap
      ↓
Requests
      ↓
BeautifulSoup
      ↓
Raw HTML
      ↓
Pandas DataFrame
      ↓
Market Metrics
      ↓
Plotly Visualizations
      ↓
Streamlit Dashboard
```

## Data Engineering Concepts Demonstrated

This project demonstrates several practical data engineering and analytics concepts:

1. Data extraction from a live web source
2. HTML parsing
3. Data cleaning and numeric conversion
4. Structured data transformation
5. Caching
6. Error handling
7. Exploratory data analysis
8. KPI generation
9. Interactive dashboard development
10. Data export

## Limitations

- The CoinMarketCap HTML structure may change and break the scraper.
- This project is designed for educational and portfolio purposes.
- Market information is retrieved from external services and may be temporarily unavailable.
- The portfolio feature is a **paper simulation** and does not execute trades.
- Cryptocurrency prices are volatile; the dashboard should not be treated as financial advice.

## Future Improvements

Potential next steps:

- Replace HTML scraping with an official market-data API where appropriate
- Store historical snapshots in PostgreSQL or another database
- Build historical price and volume time series
- Add technical indicators
- Add price alerts
- Add automated scheduled data collection
- Add machine-learning-based price or volatility analysis
- Add Docker deployment
- Deploy the Streamlit dashboard publicly
- Add automated tests and CI/CD

## Portfolio Value

This project demonstrates an end-to-end workflow:

**Web Scraping → Data Cleaning → Data Engineering → Analytics → Visualization → Dashboard Development**

It can therefore be used as a portfolio project to demonstrate practical Python, data analysis, web scraping, visualization, and application-development skills.

## Disclaimer

This project is for educational and portfolio purposes only. It does not provide investment advice, and the paper portfolio does not execute real cryptocurrency transactions.
