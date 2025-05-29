import ccxt
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime
import streamlit as st
from io import BytesIO

# === Streamlit Ayarları ===
st.set_page_config(layout="wide")
st.title("BinanceUS Kripto Tarama - AVWAP & Volume Profile")

# === BinanceUS USDT Pariteleri Al ===
@st.cache_data
def fetch_binance_usdt_symbols():
    exchange = ccxt.binanceus()
    markets = exchange.load_markets()
    symbols_info = []
    for symbol, market in markets.items():
        if symbol.endswith('/USDT') and market['active']:
            symbols_info.append((symbol, market['info'].get('baseAsset', symbol.split('/')[0]), market['info'].get('baseAssetName')))
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
        except Exception as e:
            print(f"{symbol} verisi alınırken hata: {e}")
            break
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# === AVWAP Hesapla ===
def calculate_avwap(df, anchor_date="2020-03-18"):
    anchor_ts = pd.to_datetime(anchor_date)
    start_point = anchor_ts if df["timestamp"].min() <= anchor_ts else df["timestamp"].iloc[1]
    df = df[df["timestamp"] >= start_point]
    if df.empty or df["volume"].sum() == 0:
        return None, None
    tp = (df["high"] + df["low"] + df["close"]) / 3
    avwap = (tp * df["volume"]).sum() / df["volume"].sum()
    std = np.sqrt(np.mean((tp - avwap) ** 2))
    return avwap, avwap + 4 * std

# === Volume Profile ===
def compute_volume_profile(df, tick_size=0.01, row_param=50):
    high, low = df['high'].max(), df['low'].min()
    price_range = high - low
    price_step = max(tick_size, round((price_range / row_param) / tick_size) * tick_size)
    bin_edges = np.arange(low, high + price_step, price_step)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    volume_sum = np.zeros(len(bin_centers))
    for i in range(len(df)):
        price = df['close'].iloc[i]
        volume = df['volume'].iloc[i]
        if pd.isna(price) or pd.isna(volume):
            continue
        bin_idx = int((price - low) // price_step)
        if 0 <= bin_idx < len(bin_centers):
            volume_sum[bin_idx] += volume
    return pd.DataFrame({'price_level': bin_centers, 'total_volume': volume_sum})

# === VAL VAH ===
def calculate_value_area_range(vp_df, value_area_pct=0.7):
    df = vp_df[vp_df['total_volume'] > 0].sort_values(by='price_level').reset_index(drop=True)
    total_volume = df['total_volume'].sum()
    target_volume = total_volume * value_area_pct
    min_range_width = float('inf')
    val = vah = None
    for i in range(len(df)):
        cum_volume = 0
        for j in range(i, len(df)):
            cum_volume += df.at[j, 'total_volume']
            if cum_volume >= target_volume:
                width = df.at[j, 'price_level'] - df.at[i, 'price_level']
                if width < min_range_width:
                    min_range_width = width
                    val, vah = df.at[i, 'price_level'], df.at[j, 'price_level']
                break
    return val, vah

# === Coingecko API ile temel veriler ===
def get_coingecko_market_data(coin_name):
    try:
        search_url = f"https://api.coingecko.com/api/v3/search?query={coin_name}"
        r = requests.get(search_url)
        coins = r.json()['coins']
        if not coins:
            return None
        coin_id = coins[0]['id']
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        r = requests.get(url)
        data = r.json()
        return {
            "Market Cap": data['market_data'].get('market_cap', {}).get('usd'),
            "Circulating Supply": data['market_data'].get('circulating_supply'),
            "Total Supply": data['market_data'].get('total_supply'),
            "TVL": data.get('market_data', {}).get('total_value_locked', {}).get('usd')
        }
    except:
        return None

# === Sembol Analiz Et ===
def analyze_symbol(symbol, token_code, token_long):
    df = fetch_ohlcv_data_binance(symbol)
    if df.empty or len(df) < 100:
        return None
    ath_price = df['high'].max()
    ath_date = df[df['high'] == ath_price]['timestamp'].iloc[0]
    last_price = df['close'].iloc[-1]
    last_date = df['timestamp'].iloc[-1]
    pct_down = ((ath_price - last_price) / ath_price * 100)
    day_diff = (last_date - ath_date).days
    avwap, avwap_upper = calculate_avwap(df)
    pct_from_avwap = ((last_price - avwap) / avwap * 100) if avwap else None
    pct_from_upper = ((last_price - avwap_upper) / avwap_upper * 100) if avwap_upper else None
    vp_df = df[df['timestamp'] >= ath_date]
    vp = compute_volume_profile(vp_df)
    poc = vp.loc[vp['total_volume'].idxmax(), 'price_level'] if not vp.empty else None
    val, vah = calculate_value_area_range(vp) if not vp.empty else (None, None)
    pct_from_poc = ((last_price - poc) / poc * 100) if poc else None
    pct_from_val = ((last_price - val) / val * 100) if val else None
    vp_band_width = ((vah - val) / (ath_price - val) * 100) if val and vah else None
    gecko_data = get_coingecko_market_data(token_long)
    return [symbol, token_code, token_long, round(ath_price, 4), ath_date.date(), round(last_price, 4), last_date.date(),
            round(pct_down, 2), day_diff, round(avwap, 4) if avwap else None, round(avwap_upper, 4) if avwap_upper else None,
            round(pct_from_avwap, 2) if pct_from_avwap else None, round(pct_from_upper, 2) if pct_from_upper else None,
            round(poc, 4) if poc else None, round(val, 4) if val else None, round(vah, 4) if vah else None,
            round(pct_from_poc, 2) if pct_from_poc else None, round(pct_from_val, 2) if pct_from_val else None,
            round(vp_band_width, 2) if vp_band_width else None,
            gecko_data['Market Cap'] if gecko_data else None,
            gecko_data['Circulating Supply'] if gecko_data else None,
            gecko_data['Total Supply'] if gecko_data else None,
            gecko_data['TVL'] if gecko_data else None]

# === Ana İşlem ===
symbols_info = fetch_binance_usdt_symbols()
results = []
for symbol, token_code, token_long in symbols_info[:20]:  # ilk 20 ile sınırlandı
    row = analyze_symbol(symbol, token_code, token_long)
    if row:
        results.append(row)

columns = ["Symbol", "Token", "Token Adı", "ATH", "ATH Tarihi", "Son Fiyat", "Son Tarih", "ATH'den % Fark", "Gün Sayısı",
           "AVWAP", "AVWAP +4σ", "% Fark AVWAP", "% Fark +4σ", "POC", "VAL", "VAH", "% Fark POC", "% Fark VAL",
           "VP Genişliği (%)", "Market Cap", "Circulating Supply", "Total Supply", "TVL"]
df_result = pd.DataFrame(results, columns=columns)
st.dataframe(df_result, use_container_width=True)

# === Excel Export ===
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

excel_data = convert_df_to_excel(df_result)
st.download_button("Excel olarak indir", data=excel_data, file_name="kripto_analiz.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
