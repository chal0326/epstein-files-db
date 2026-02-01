#!/usr/bin/env python3
"""Streamlit app to explore Epstein files database."""

import sqlite3
import pandas as pd
import streamlit as st
from pathlib import Path

DB_PATH = Path("./epstein_files/epstein.db")
BASE_DIR = Path("./epstein_files")


@st.cache_resource
def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def main():
    st.set_page_config(page_title="Epstein Files Explorer", layout="wide")
    st.title("Epstein Files Explorer")
    st.caption("60,000+ DOJ files | 146M+ characters extracted | 178 keywords searched")

    conn = get_db()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Overview", "Keyword Search", "Browse Files", "Full-Text Search", "Dataset Stats"
    ])

    # ── TAB 1: OVERVIEW ──
    with tab1:
        col1, col2, col3, col4 = st.columns(4)

        total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        total_text = conn.execute("SELECT COUNT(*) FROM text_cache").fetchone()[0]
        total_chars = conn.execute("SELECT SUM(char_count) FROM text_cache").fetchone()[0] or 0
        total_keywords = conn.execute("SELECT COUNT(DISTINCT keyword) FROM search_results").fetchone()[0]
        total_matches = conn.execute("SELECT SUM(match_count) FROM search_results").fetchone()[0] or 0
        needs_ocr = conn.execute("SELECT COUNT(*) FROM files WHERE needs_ocr = 1").fetchone()[0]

        col1.metric("Total PDF Files", f"{total_files:,}")
        col2.metric("Text Extracted", f"{total_text:,}")
        col3.metric("Total Characters", f"{total_chars / 1_000_000:.1f}M")
        col4.metric("Keyword Matches", f"{total_matches:,}")

        st.markdown("---")

        # Dataset breakdown
        st.subheader("Files by Dataset")
        df_ds = pd.read_sql_query("""
            SELECT dataset as 'Dataset',
                   COUNT(*) as 'Files',
                   ROUND(SUM(file_size) / 1024.0 / 1024.0, 1) as 'Size (MB)',
                   SUM(has_text) as 'Has Text',
                   SUM(needs_ocr) as 'Needs OCR'
            FROM files GROUP BY dataset ORDER BY dataset
        """, conn)
        st.dataframe(df_ds, use_container_width=True, hide_index=True)

        # Production files
        st.subheader("Production Files (DS10)")
        df_prod = pd.read_sql_query("""
            SELECT file_type as 'Type',
                   COUNT(*) as 'Count',
                   ROUND(SUM(file_size) / 1024.0 / 1024.0, 1) as 'Size (MB)'
            FROM production_files GROUP BY file_type ORDER BY COUNT(*) DESC
        """, conn)
        st.dataframe(df_prod, use_container_width=True, hide_index=True)

        st.subheader("The Gap")
        st.markdown(f"""
        - **DOJ claimed:** 3.5 million pages
        - **Actual files found:** {total_files:,}
        - **Files with extractable text:** {total_text:,}
        - **Files needing OCR:** {needs_ocr:,}
        - **EFTA ID slots checked:** ~2.7 million
        - **Fill rate:** ~0.08%
        - **99.92% of file slots are empty**
        """)

    # ── TAB 2: KEYWORD SEARCH RESULTS ──
    with tab2:
        st.subheader("Keyword Hit Summary")

        # Get all keywords with counts
        df_kw = pd.read_sql_query("""
            SELECT keyword as 'Keyword',
                   COUNT(*) as 'Files',
                   SUM(match_count) as 'Total Matches'
            FROM search_results
            GROUP BY keyword
            ORDER BY SUM(match_count) DESC
        """, conn)

        # Filter controls
        col1, col2 = st.columns([1, 3])
        with col1:
            min_matches = st.number_input("Min matches", value=10, min_value=0)
        df_filtered = df_kw[df_kw["Total Matches"] >= min_matches]

        st.dataframe(df_filtered, use_container_width=True, hide_index=True, height=400)

        st.markdown("---")

        # Drill into a keyword
        st.subheader("Keyword Detail")
        keyword_list = df_kw["Keyword"].tolist()
        if keyword_list:
            selected_kw = st.selectbox("Select keyword", keyword_list)

            df_detail = pd.read_sql_query("""
                SELECT f.filename as 'File',
                       f.dataset as 'Dataset',
                       sr.match_count as 'Matches',
                       sr.context as 'Context'
                FROM search_results sr
                JOIN files f ON f.id = sr.file_id
                WHERE sr.keyword = ?
                ORDER BY sr.match_count DESC
                LIMIT 100
            """, conn, params=[selected_kw])

            st.write(f"**{selected_kw}**: {len(df_detail)} files (showing top 100)")
            st.dataframe(df_detail, use_container_width=True, hide_index=True, height=400)

    # ── TAB 3: BROWSE FILES ──
    with tab3:
        st.subheader("Browse Files")

        col1, col2, col3 = st.columns(3)
        with col1:
            datasets = conn.execute("SELECT DISTINCT dataset FROM files ORDER BY dataset").fetchall()
            ds_options = ["All"] + [str(d[0]) for d in datasets]
            selected_ds = st.selectbox("Dataset", ds_options)
        with col2:
            search_filename = st.text_input("Filename contains", "")
        with col3:
            text_filter = st.selectbox("Text status", ["All", "Has text", "Needs OCR", "No text"])

        query = "SELECT f.id, f.filename, f.dataset, f.file_size, f.has_text, f.needs_ocr, f.rel_path FROM files f WHERE 1=1"
        params = []

        if selected_ds != "All":
            query += " AND f.dataset = ?"
            params.append(int(selected_ds))
        if search_filename:
            query += " AND f.filename LIKE ?"
            params.append(f"%{search_filename}%")
        if text_filter == "Has text":
            query += " AND f.has_text = 1"
        elif text_filter == "Needs OCR":
            query += " AND f.needs_ocr = 1"
        elif text_filter == "No text":
            query += " AND f.has_text = 0 AND f.needs_ocr = 0"

        query += " ORDER BY f.dataset, f.filename LIMIT 500"

        df_files = pd.read_sql_query(query, conn, params=params)
        st.write(f"Showing {len(df_files)} files (limit 500)")
        st.dataframe(df_files, use_container_width=True, hide_index=True, height=400)

        # View file text
        st.markdown("---")
        st.subheader("View Extracted Text")
        file_id_input = st.number_input("Enter file ID to view text", min_value=1, value=1)

        if st.button("Load Text"):
            row = conn.execute("""
                SELECT f.filename, f.rel_path, tc.extracted_text, tc.char_count, tc.method
                FROM files f
                LEFT JOIN text_cache tc ON tc.file_id = f.id
                WHERE f.id = ?
            """, (file_id_input,)).fetchone()

            if row:
                fname, rel_path, text, char_count, method = row
                st.write(f"**{fname}** | Path: `{rel_path}` | Method: {method} | Chars: {char_count:,}" if text else f"**{fname}** - No text extracted")
                if text:
                    st.text_area("Extracted text", text, height=400)
            else:
                st.warning("File ID not found")

    # ── TAB 4: FULL-TEXT SEARCH ──
    with tab4:
        st.subheader("Search All Extracted Text")
        st.caption("Search across 146M+ characters of extracted text")

        search_term = st.text_input("Search term (case-insensitive)")

        if search_term and st.button("Search"):
            results_container = st.empty()
            status = st.status(f"Searching 146M+ chars for '{search_term}'...", expanded=True)
            results_area = st.container()

            # Stream results as they come in
            cursor = conn.execute("""
                SELECT f.id, f.filename, f.dataset, f.rel_path, tc.extracted_text
                FROM text_cache tc
                JOIN files f ON f.id = tc.file_id
                WHERE tc.extracted_text LIKE ?
                LIMIT 200
            """, (f"%{search_term}%",))

            hit_count = 0
            results = []
            batch_size = 10

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                results.extend(rows)
                hit_count += len(rows)
                status.update(label=f"Found {hit_count} files so far...", expanded=True)

            status.update(label=f"Done - {hit_count} files found", state="complete", expanded=False)

            for fid, fname, ds, rel_path, text in results:
                # Find context around match
                lower_text = text.lower()
                idx = lower_text.find(search_term.lower())
                if idx >= 0:
                    start = max(0, idx - 200)
                    end = min(len(text), idx + len(search_term) + 200)
                    context = text[start:end]
                    # Bold the match
                    match_start = idx - start
                    match_end = match_start + len(search_term)
                    highlighted = (
                        context[:match_start]
                        + "**" + context[match_start:match_end] + "**"
                        + context[match_end:]
                    )
                else:
                    highlighted = text[:400]

                with results_area.expander(f"[DS{ds}] {fname} (ID: {fid})"):
                    st.markdown(f"Path: `{rel_path}`")
                    st.markdown(f"...{highlighted}...")

    # ── TAB 5: DATASET STATS ──
    with tab5:
        st.subheader("Bruteforce Audit Results")

        st.markdown("""
        | Dataset | EFTA Range | Total Slots | Files Found | Fill Rate |
        |---------|-----------|-------------|-------------|-----------|
        | 8 | 00000001-00423792 | 423,792 | ~11 | ~0.003% |
        | 9 | 00423793-01262781 | 838,989 | 807 | 0.096% |
        | 10 | 01262782-02212882 | 950,101 | 54,987 | ~5.8%* |
        | 11 | 02212883-02730264 | 517,382 | 408 | 0.079% |

        *DS10 high count is from browser-scraped listing pages, not bruteforce alone (686 from bruteforce).
        """)

        st.subheader("File Size Distribution")
        df_sizes = pd.read_sql_query("""
            SELECT
                CASE
                    WHEN file_size < 10240 THEN '< 10KB'
                    WHEN file_size < 102400 THEN '10KB - 100KB'
                    WHEN file_size < 1048576 THEN '100KB - 1MB'
                    WHEN file_size < 10485760 THEN '1MB - 10MB'
                    ELSE '> 10MB'
                END as 'Size Range',
                COUNT(*) as 'Count'
            FROM files
            GROUP BY 1
            ORDER BY MIN(file_size)
        """, conn)
        st.bar_chart(df_sizes.set_index("Size Range"))

        st.subheader("Text Extraction Stats")
        df_text = pd.read_sql_query("""
            SELECT
                CASE
                    WHEN char_count < 100 THEN '< 100 chars'
                    WHEN char_count < 1000 THEN '100 - 1K chars'
                    WHEN char_count < 10000 THEN '1K - 10K chars'
                    WHEN char_count < 100000 THEN '10K - 100K chars'
                    ELSE '> 100K chars'
                END as 'Text Length',
                COUNT(*) as 'Files'
            FROM text_cache
            GROUP BY 1
            ORDER BY MIN(char_count)
        """, conn)
        st.bar_chart(df_text.set_index("Text Length"))


if __name__ == "__main__":
    main()
