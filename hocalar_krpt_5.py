import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(layout="wide")
st.title("Hocalar Kripto")

# === Convert Google Sheets URLs to export CSV format ===
def convert_edit_url_to_csv(url):
    return url.split("/edit")[0] + "/export?format=csv"

# === Load Data from Google Sheets ===
@st.cache_data(ttl=0)
def load_google_sheet(url):
    try:
        csv_url = convert_edit_url_to_csv(url)
        df = pd.read_csv(csv_url)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading sheet: {e}")
        return pd.DataFrame()

# === URLs ===
#url1 = "https://docs.google.com/spreadsheets/d/1lPP3BdIVMGAijVp5OWUbE-rGO-PRrUCT9AtKblg_lTs/edit?usp=drivesdk"
url1 = "https://docs.google.com/spreadsheets/d/12w2gEAIxLlumDWG_kzXfO0lB5EdTim6_mnOR1uhVB_0/edit?usp=drivesdk"
#url2 = "https://docs.google.com/spreadsheets/d/1E8JmmVTtaxLFWJBYj2bVMhaYVydF9Cv-qJ5V415IvYs/edit?usp=drivesdk"
url2 = "https://docs.google.com/spreadsheets/d/14CRP9oM7852jl3X7C8KeXKjvwZsR9sXtUnzYWIii0CA/edit?usp=drivesdk"

# === Load Sheets ===
# Guncel sayfa GID’sini elle belirle
#df1 = load_google_sheet(convert_edit_url_to_csv(url1, gid="0"))  # örnek GID değeri (ilk sekme genelde "0" olur)
df1 = load_google_sheet(url1)
df2 = load_google_sheet(url2)

# === Normalize Token Names for Merge ===
if "Token" in df1.columns:
    df1["Token"] = df1["Token"].str.replace("/USDT", "", regex=False).str.strip()

# === Merge using Token <-> Sembol ===
if "Token" in df1.columns and "Sembol" in df2.columns:
    merged = pd.merge(df1, df2, left_on="Token", right_on="Sembol", how="left")
else:
    st.error("Required columns 'Token' and 'Sembol' not found in the sheets.")
    st.stop()

# === Sidebar: Column Selector ===
st.sidebar.header("Filter Options")

non_numeric_cols = [col for col in merged.columns if not pd.api.types.is_numeric_dtype(merged[col])]
numeric_cols = [col for col in merged.columns if pd.api.types.is_numeric_dtype(merged[col])]

# Column selection
selected_columns = st.sidebar.multiselect(
    "Select columns to display",
    merged.columns.tolist(),
    default=merged.columns.tolist()
)

filtered_df = merged.copy()

# Numeric slider filters
for col in numeric_cols:
    min_val = float(filtered_df[col].min())
    max_val = float(filtered_df[col].max())
    if pd.notna(min_val) and pd.notna(max_val) and min_val != max_val:
        selected_range = st.sidebar.slider(
            f"{col} range", min_val, max_val, (min_val, max_val)
        )
        filtered_df = filtered_df[(filtered_df[col] >= selected_range[0]) & (filtered_df[col] <= selected_range[1])]

# === Display Table ===
# st.dataframe(filtered_df[selected_columns], use_container_width=True)
# === Display Table ===

# ➤ Seçilen kolonlardan tamamı boş olanları çıkar
filtered_df = filtered_df[selected_columns].dropna(axis=1, how="all")

# (İsteğe bağlı) Seçilen kolon listesini de güncelle
selected_columns = filtered_df.columns.tolist()

# Veri çerçevesini göster
st.dataframe(filtered_df, use_container_width=True)

# === Excel Export ===
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="MergedData")
    return output.getvalue()

excel_data = convert_df_to_excel(filtered_df[selected_columns])
st.download_button(
    label="📥 Excel Olarak İndir",
    data=excel_data,
    file_name="hocalar_kripto.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
