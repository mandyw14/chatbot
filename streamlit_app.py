# app.py
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Author & Content Search", layout="wide")

CSV_PATH = "Dimensions-Publication-2025-10-14_15-57-25.csv"

# Expected column names (with a tiny bit of resilience for MeSH terms)
COL_AUTHORS = "Authors"
COL_TITLE   = "Title"
COL_ABS     = "Abstract"
MESH_CANDIDATES = ["MeSH terms", "MeSH_terms", "Mesh Terms", "Keywords", "Key Terms"]  # we'll pick the first that exists

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

st.title("Welcome to the Branch Out Science Search")

if df.empty:
    st.stop()

# Validate core columns
missing = [c for c in [COL_AUTHORS, COL_TITLE, COL_ABS] if c not in df.columns]
if missing:
    st.error(f"Missing expected column(s): {', '.join(missing)}")
    st.caption(f"Available columns include: {', '.join(map(str, df.columns[:20]))}...")
    st.stop()

# Resolve MeSH/keywords column if present
mesh_col = next((c for c in MESH_CANDIDATES if c in df.columns), None)

# --- Inputs ---
st.sidebar.header("Filters")

author_query = st.sidebar.text_input(
    "Author contains",
    value="",
    placeholder="e.g., Sohn"
)

content_query = st.sidebar.text_input(
    "Content keyword (Title/Abstract/MeSH)",
    value="",
    placeholder="e.g., mindfulness"
)

# Let user choose which fields to search for the content keyword
field_options = ["Title", "Abstract"] + (["MeSH terms"] if mesh_col else [])
selected_fields = st.sidebar.multiselect(
    "Search keyword in:",
    options=field_options,
    default=field_options
)

# --- Filtering logic ---
results = df.copy()

# Authors filter (case-insensitive substring)
if author_query.strip():
    results = results[results[COL_AUTHORS].astype(str).str.contains(author_query.strip(), case=False, na=False)]

# Content keyword filter (OR across selected fields)
if content_query.strip() and selected_fields:
    masks = []
    for field in selected_fields:
        if field == "Title":
            masks.append(results[COL_TITLE].astype(str).str.contains(content_query, case=False, na=False))
        elif field == "Abstract":
            masks.append(results[COL_ABS].astype(str).str.contains(content_query, case=False, na=False))
        elif field == "MeSH terms" and mesh_col:
            masks.append(results[mesh_col].astype(str).str.contains(content_query, case=False, na=False))
    if masks:
        any_mask = masks[0]
        for m in masks[1:]:
            any_mask |= m
        results = results[any_mask]

# --- KPIs ---
c1, c2 = st.columns(2)
c1.metric("Total rows", f"{len(df):,}")
c2.metric("Matches", f"{len(results):,}")

# --- Table ---
# Put key columns up front if present
front_cols = [COL_TITLE, COL_AUTHORS, COL_ABS] + ([mesh_col] if mesh_col else [])
front_cols = [c for c in front_cols if c is not None]
other_cols = [c for c in results.columns if c not in front_cols]
ordered = results[front_cols + other_cols] if front_cols else results

st.subheader("Results")
st.dataframe(ordered, use_container_width=True)

# --- Download ---
st.download_button(
    "Download results (CSV)",
    data=ordered.to_csv(index=False).encode("utf-8-sig"),
    file_name="dimensions_filtered_results.csv",
    mime="text/csv",
)

# --- Hints ---
with st.expander("Notes"):
    st.markdown(
        """
- **Author contains** matches substrings in the **Authors** column (case-insensitive).
- **Content keyword** matches substrings (case-insensitive) in the selected fields.
- If your file uses a different column for MeSH/keywords (e.g., `Keywords`), the app will use it automatically.
        """
    )
