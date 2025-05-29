import ccxt
import pandas as pd
import numpy as np
import time
import requests
import streamlit as st
from io import BytesIO

# === Streamlit Ayarları ===
st.set_page_config(layout="wide")
st.sidebar.title("Filtre Ayarları")
st.title("BinanceUS Kripto Tarama - AVWAP & CoinGecko Verileri")

# === Binance Sembollerini ve Uzun İsimleri Al ===
@st.cache_data
def fetch_binance_usdt_symbols():
    exchange = ccxt.binanceus()
    markets = exchange.load_markets()
    symbols_info = []
    for symbol, market in markets.items():
        if symbol.endswith('/USDT') and market['active']:
            base_symbol = market['base']
            base_name = market.get('info', {}).get('baseAssetName') or base_symbol
            symbols_info.append((symbol, base_symbol, base_name))
    return symbols_info

# === OHLCV Verisi Al ===
def fetch_ohlcv_data_binance(symbol):
    exchange = ccxt.binanceus()
    since = exchange.parse8601('2019-01-01T00:00:00Z')
    ohlcv = []
    while since < exchange.milliseconds():
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe='1d', since=since, limit=1000)
            if not data:
                break
            ohlcv.extend(data)
            since = data[-1][0] + 86400000
            time.sleep(1.5)
        except:
            break

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# === AVWAP Hesapla ===
def calculate_avwap(df, anchor_date="2020-03-18"):
    avwap_anchor_date = pd.to_datetime(anchor_date)
    start_point = avwap_anchor_date if df["timestamp"].min() <= avwap_anchor_date else df["timestamp"].iloc[1]
    avwap_df = df[df["timestamp"] >= start_point].copy()
    if avwap_df.empty or avwap_df["volume"].sum() == 0:
        return None, None
    tp = (avwap_df["high"] + avwap_df["low"] + avwap_df["close"]) / 3
    volume = avwap_df["volume"]
    avwap = (tp * volume).sum() / volume.sum()
    std = np.sqrt(np.mean((tp - avwap) ** 2)) if len(tp) > 1 else 0
    return avwap, avwap + 4 * std

# === CoinGecko Coin Listesi ===
@st.cache_data
def get_coingecko_coin_list():
    url = "https://api.coingecko.com/api/v3/coins/list"
    response = requests.get(url)
    coins = response.json()
    return {coin['name'].lower(): coin['id'] for coin in coins}

# === CoinGecko Verisi Al ===
def get_coingecko_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    try:
        response = requests.get(url)
        data = response.json()
        market_data = data.get("market_data", {})
        tvl = data.get("tvl", None) or data.get("public_interest_score", None)  # fallback
        return {
            "Market Cap": market_data.get("market_cap", {}).get("usd"),
            "Circulating Supply": market_data.get("circulating_supply"),
            "Total Supply": market_data.get("total_supply"),
            "TVL": tvl
        }
    except:
        return {"Market Cap": None, "Circulating Supply": None, "Total Supply": None, "TVL": None}

# === Analiz Fonksiyonu ===
def analyze_symbol(symbol, token_code, token_name, gecko_map):
    df = fetch_ohlcv_data_binance(symbol)
    if df.empty or len(df) < 100:
        return None

    ath_price = df["high"].max()
    ath_date = df[df["high"] == ath_price]["timestamp"].iloc[0]
    latest_close = df["close"].iloc[-1]
    latest_date = df["timestamp"].iloc[-1]
    pct_down = ((ath_price - latest_close) / ath_price * 100)
    day_diff = (latest_date - ath_date).days
    avwap, avwap_upper = calculate_avwap(df)
    pct_from_avwap = ((latest_close - avwap) / avwap * 100) if avwap else None
    pct_from_upper = ((latest_close - avwap_upper) / avwap_upper * 100) if avwap_upper else None

    gecko_id = gecko_map.get(token_name.lower()) or gecko_map.get(token_code.lower())
    gecko_data = get_coingecko_data(gecko_id) if gecko_id else {"Market Cap": None, "Circulating Supply": None, "Total Supply": None, "TVL": None}

    return [symbol, token_name, round(ath_price, 4), ath_date.date(), round(latest_close, 4), latest_date.date(),
            round(pct_down, 2), day_diff, round(avwap, 4) if avwap else None, round(avwap_upper, 4) if avwap_upper else None,
            round(pct_from_avwap, 2) if pct_from_avwap else None, round(pct_from_upper, 2) if pct_from_upper else None,
            gecko_data["Market Cap"], gecko_data["Circulating Supply"], gecko_data["Total Supply"], gecko_data["TVL"]]

# === Ana İşlem ===
st.info("Veriler BinanceUS ve CoinGecko'dan çekiliyor, lütfen bekleyin...")
symbols_info = fetch_binance_usdt_symbols()
gecko_map = get_coingecko_coin_list()
results = []

for symbol, token_code, token_name in symbols_info[:20]:
    row = analyze_symbol(symbol, token_code, token_name, gecko_map)
    if row:
        results.append(row)

columns = ["Symbol", "Token Adı", "ATH", "ATH Tarihi", "Son Fiyat", "Son Tarih", "ATH'den % Fark", "Gün Sayısı",
           "AVWAP", "AVWAP +4σ", "% Fark AVWAP", "% Fark +4σ",
           "Market Cap", "Circulating Supply", "Total Supply", "TVL"]
df_result = pd.DataFrame(results, columns=columns)

# === Filtreleme ===
st.dataframe(df_result, use_container_width=True)

# === Excel İndirme ===
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

excel_data = convert_df_to_excel(df_result)
st.download_button("Excel olarak indir", data=excel_data, file_name="kripto_analiz.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
