# app.py
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Quick Author Search", layout="wide")

CSV_PATH = "Dimensions-Publication-2025-10-14_15-57-25.csv"
AUTHOR_COL = "Authors"   # exact column name expected in the CSV

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding_errors="ignore")
    except FileNotFoundError:
        st.error(f"File not found: {path}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return pd.DataFrame()

df = load_data(CSV_PATH)

st.title("Dimensions: Simple Author Search")

if df.empty:
    st.stop()

# Basic column check
if AUTHOR_COL not in df.columns:
    st.error(
        f"Column '{AUTHOR_COL}' not found. "
        f"Available columns include: {', '.join(df.columns[:20])}..."
    )
    st.stop()

# User input for substring search
author_query = st.text_input(
    "Enter an author substring to search (e.g., 'Sohn')",
    value="",
    placeholder="Type a last name or fragment..."
)

# Build mask (case-insensitive contains)
if author_query.strip():
    mask = df[AUTHOR_COL].astype(str).str.contains(author_query.strip(), case=False, na=False)
    results = df[mask].copy()
else:
    results = df.copy()

# KPIs
c1, c2 = st.columns(2)
c1.metric("Total rows", f"{len(df):,}")
c2.metric("Matches", f"{len(results):,}")

# Show table
st.subheader("Results")
st.dataframe(results, use_container_width=True)

# Download filtered results
st.download_button(
    "Download matches as CSV",
    data=results.to_csv(index=False).encode("utf-8-sig"),
    file_name="author_search_results.csv",
    mime="text/csv",
)
