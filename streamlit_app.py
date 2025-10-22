# app.py
import re
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dimensions Search + Chat", layout="wide")

CSV_PATH = "Dimensions-Publication-2025-10-14_15-57-25.csv"

# Expected column names
COL_AUTHORS = "Authors"
COL_TITLE   = "Title"
COL_ABS     = "Abstract"
MESH_CANDIDATES = ["MeSH terms", "MeSH_terms", "Mesh Terms", "Keywords", "Key Terms"]

# -------------------------------------------------
# Data load
# -------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding_errors="ignore")

try:
    df = load_data(CSV_PATH)
except FileNotFoundError:
    st.error(f"File not found: {CSV_PATH}")
    st.stop()
except Exception as e:
    st.error(f"Could not read CSV: {e}")
    st.stop()

st.title("Dimensions: Simple Search + Chatbot")

# Validate core columns
missing = [c for c in [COL_AUTHORS, COL_TITLE, COL_ABS] if c not in df.columns]
if missing:
    st.error(f"Missing expected column(s): {', '.join(missing)}")
    st.caption(f"Available columns include: {', '.join(map(str, df.columns[:20]))}...")
    st.stop()

mesh_col = next((c for c in MESH_CANDIDATES if c in df.columns), None)

# -------------------------------------------------
# Sidebar: Filters
# -------------------------------------------------
st.sidebar.header("Filters")

author_query = st.sidebar.text_input("Authors contains", value="", placeholder="e.g., Sohn")
content_query = st.sidebar.text_input("Content keyword", value="", placeholder="e.g., mindfulness")

field_options = ["Title", "Abstract"] + (["MeSH terms"] if mesh_col else [])
selected_fields = st.sidebar.multiselect(
    "Search keyword in:",
    options=field_options,
    default=field_options
)

# Apply filters
results = df.copy()

if author_query.strip():
    results = results[results[COL_AUTHORS].astype(str).str.contains(author_query.strip(), case=False, na=False)]

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

# KPIs
k1, k2 = st.columns(2)
k1.metric("Total rows", f"{len(df):,}")
k2.metric("Matches", f"{len(results):,}")

# Results table
front_cols = [COL_TITLE, COL_AUTHORS, COL_ABS] + ([mesh_col] if mesh_col else [])
front_cols = [c for c in front_cols if c is not None]
other_cols = [c for c in results.columns if c not in front_cols]
ordered = results[front_cols + other_cols] if front_cols else results

st.subheader("Results")
st.dataframe(ordered, use_container_width=True)

# Download
st.download_button(
    "Download results (CSV)",
    data=ordered.to_csv(index=False).encode("utf-8-sig"),
    file_name="dimensions_filtered_results.csv",
    mime="text/csv",
)

st.divider()

# =================================================
# Chatbot section
# =================================================
st.header("Chat with your data")

use_filtered = st.checkbox("Chat over current FILTERED results (otherwise uses ALL rows)", value=True)

# Session state for chat
if "messages" not in st.session_state:
    st.session_state.messages = []

def _extract_top_n(text: str, default: int = 10) -> int:
    m = re.search(r"\btop\s+(\d+)\b", text, re.IGNORECASE)
    if m:
        return max(1, int(m.group(1)))
    m2 = re.search(r"\b(\d+)\b", text)  # fallback: first number
    return max(1, int(m2.group(1))) if m2 else default

def _safe_series_counts(series: pd.Series, split_semicolon=True) -> pd.Series:
    s = series.dropna().astype(str)
    if split_semicolon and s.str.contains(";").mean() > 0.3:
        s = s.str.split(";").explode().str.strip()
    s = s[s != ""]
    return s.value_counts()

def route_query(q: str, data: pd.DataFrame) -> Tuple[str, Optional[pd.DataFrame]]:
    """
    Very lightweight intent routing for common dataset Q&A.
    Returns (text_response, optional_dataframe_to_show)
    """
    q_lower = q.lower().strip()

    # Reset
    if q_lower in {"clear", "clear chat", "reset"}:
        st.session_state.messages = []
        return "Chat cleared.", None

    # Help
    if any(w in q_lower for w in ["help", "what can you do", "commands", "options"]):
        return (
            "You can ask things like:\n"
            "- **how many rows?** or **how many matches?**\n"
            "- **top 10 authors** / **top institutions 5**\n"
            "- **list titles** (optionally: **list titles mentioning ketamine**)\n"
            "- **what columns are available?**\n"
            "- **summary** (basic dataset summary)\n"
            "- **clear chat**",
            None,
        )

    # Row counts
    if "how many" in q_lower and ("row" in q_lower or "match" in q_lower):
        return f"There are **{len(data):,}** rows in the current scope.", None

    # Columns
    if "column" in q_lower and ("what" in q_lower or "list" in q_lower or "available" in q_lower):
        cols = ", ".join(map(str, data.columns))
        return f"Available columns:\n\n{cols}", None

    # Summary
    if "summary" in q_lower:
        text = (
            f"- Rows: **{len(data):,}**\n"
            f"- Columns: **{data.shape[1]}**\n"
            f"- Example columns: {', '.join(map(str, data.columns[:10]))}"
        )
        return text, None

    # Top authors / institutions
    if "top" in q_lower and "author" in q_lower:
        n = _extract_top_n(q_lower, default=10)
        if COL_AUTHORS in data.columns:
            vc = _safe_series_counts(data[COL_AUTHORS]).head(n)
            df_out = vc.reset_index()
            df_out.columns = ["Author", "Count"]
            return f"Top {len(df_out)} authors:", df_out
        return "I couldn't find the Authors column.", None

    if "top" in q_lower and any(k in q_lower for k in ["institution", "affiliation", "organization"]):
        # try to guess a likely column
        inst_col = next((c for c in data.columns if c.lower() in {"institution", "institutions", "affiliation", "affiliations", "organization", "organizations"}), None)
        if inst_col:
            n = _extract_top_n(q_lower, default=10)
            vc = _safe_series_counts(data[inst_col]).head(n)
            df_out = vc.reset_index()
            df_out.columns = ["Institution", "Count"]
            return f"Top {len(df_out)} institutions:", df_out
        return "I couldn't find an Institution/Affiliation column.", None

    # List titles (optionally filtered by a word)
    if "list" in q_lower and "title" in q_lower:
        word_match = re.search(r"mentioning\s+([A-Za-z0-9\-\s]+)", q_lower)
        sub = data
        if word_match and COL_TITLE in data.columns:
            kw = word_match.group(1).strip()
            sub = sub[sub[COL_TITLE].astype(str).str.contains(kw, case=False, na=False)]
        if COL_TITLE in sub.columns:
            df_out = sub[[COL_TITLE]].head(200).copy()
            return f"Here are up to {len(df_out)} titles:", df_out
        return "I couldn't find the Title column.", None

    # Fallback
    return (
        "Sorry, I didn't recognize that. Try: **how many matches**, **top 10 authors**, "
        "**top institutions 5**, **list titles**, **what columns are available** or **summary**. "
        "Type **clear chat** to reset.",
        None,
    )

# Display prior messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if isinstance(msg["content"], pd.DataFrame):
            st.dataframe(msg["content"], use_container_width=True)
        else:
            st.markdown(msg["content"])

# Chat input
prompt = st.chat_input("Ask about your data (e.g., 'top 10 authors', 'list titles mentioning ketamine')")
if prompt:
    scope = ordered if use_filtered else df
    reply, maybe_df = route_query(prompt, scope)

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
        if maybe_df is not None:
            st.dataframe(maybe_df, use_container_width=True)
            # store the dataframe as a separate message so it's kept on reruns
            st.session_state.messages.append({"role": "assistant", "content": maybe_df})
