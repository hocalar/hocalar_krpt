import ccxt
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
import pytz
import streamlit as st
from io import BytesIO

st.set_page_config(layout="wide")
st.sidebar.title("Filtre Ayarları")
st.title("Binance Kripto Tarama - AVWAP & Volume Profile")

@st.cache_data
def fetch_binance_usdt_symbols():
    exchange = ccxt.binanceus()  # Binance yerine BinanceUS
    markets = exchange.load_markets()
    symbols_info = []
    for symbol, market in markets.items():
        if symbol.endswith('/USDT') and market['active']:
            symbols_info.append((symbol, market['info'].get('baseAsset', symbol.split('/')[0]), market.get('base', '')))
    return symbols_info

@st.cache_data
def get_coingecko_coin_list():
    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        coins = response.json()
        return {coin['name'].lower(): coin['id'] for coin in coins if 'id' in coin and 'name' in coin}
    except Exception as e:
        st.error(f"CoinGecko coin listesi alinamadi: {e}")
        return {}

def get_coingecko_data(coin_id):
    if not coin_id:
        return {"Market Cap": None, "Circulating Supply": None, "Total Supply": None, "TVL": None}
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        market_data = data.get("market_data", {})
        tvl = data.get("market_data", {}).get("total_value_locked", {}).get("usd")
        return {
            "Market Cap": market_data.get("market_cap", {}).get("usd"),
            "Circulating Supply": market_data.get("circulating_supply"),
            "Total Supply": market_data.get("total_supply"),
            "TVL": tvl
        }
    except:
        return {"Market Cap": None, "Circulating Supply": None, "Total Supply": None, "TVL": None}

# AVWAP, Volume Profile, calculate_value_area_range fonksiyonları önceki haliyle buraya eklenmeli.
# analyze_symbol fonksiyonu aşağıdaki gibi güncellenmeli:

def analyze_symbol(symbol, token_name, token_long_name, gecko_map):
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
    vp_df = df[df["timestamp"] >= ath_date]
    vp = compute_volume_profile(vp_df)
    poc = vp.loc[vp['total_volume'].idxmax(), 'price_level'] if not vp.empty else None
    val, vah = calculate_value_area_range(vp) if not vp.empty else (None, None)
    pct_from_poc = ((latest_close - poc) / poc * 100) if poc else None
    pct_from_val = ((latest_close - val) / val * 100) if val else None
    vp_band_width = ((vah - val) / (ath_price - val) * 100) if val and vah else None
    coin_id = gecko_map.get(token_long_name.lower()) if token_long_name else None
    gecko_data = get_coingecko_data(coin_id)

    return [symbol, token_name, token_long_name, round(ath_price, 4), ath_date.date(), round(latest_close, 4), latest_date.date(),
            round(pct_down, 2), day_diff, round(avwap, 4) if avwap else None, round(avwap_upper, 4) if avwap_upper else None,
            round(pct_from_avwap, 2) if pct_from_avwap else None, round(pct_from_upper, 2) if pct_from_upper else None,
            round(poc, 4) if poc else None, round(val, 4) if val else None, round(vah, 4) if vah else None,
            round(pct_from_poc, 2) if pct_from_poc else None, round(pct_from_val, 2) if pct_from_val else None,
            round(vp_band_width, 2) if vp_band_width else None,
            gecko_data["Market Cap"], gecko_data["Circulating Supply"], gecko_data["Total Supply"], gecko_data["TVL"]]

# Main
symbols_info = fetch_binance_usdt_symbols()
gecko_map = get_coingecko_coin_list()
results = []
for symbol, token_name, token_long_name in symbols_info[:20]:
    row = analyze_symbol(symbol, token_name, token_long_name, gecko_map)
    if row:
        results.append(row)

columns = ["Symbol", "Token", "Token Adı", "ATH", "ATH Tarihi", "Son Fiyat", "Son Tarih", "ATH'den % Fark", "Gün Sayısı",
           "AVWAP", "AVWAP +4σ", "% Fark AVWAP", "% Fark +4σ", "POC", "VAL", "VAH", "% Fark POC", "% Fark VAL",
           "VP Genişliği (%)", "Market Cap", "Circulating Supply", "Total Supply", "TVL"]
df_result = pd.DataFrame(results, columns=columns)
st.dataframe(df_result, use_container_width=True)

excel_data = BytesIO()
with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
    df_result.to_excel(writer, index=False)
excel_data.seek(0)

st.download_button("Excel olarak indir", data=excel_data, file_name="kripto_analiz.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
