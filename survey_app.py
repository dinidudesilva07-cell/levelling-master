import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF
from datetime import date

# Page Setup
st.set_page_config(page_title="LevelMaster Pro v8.2", page_icon="🏗️", layout="wide")

st.title("🏗️ LevelMaster Pro: Professional Field Book")
st.markdown("---")

# --- Session State Management ---
if 'field_data' not in st.session_state:
    st.session_state.field_data = []
if 'project_info' not in st.session_state:
    st.session_state.project_info = {}

# --- STEP 1: PROJECT SETUP ---
with st.expander("📂 Project Setup & Resume Work", expanded=not st.session_state.project_info):
    uploaded_draft = st.file_uploader("Resume work (Upload Draft CSV):", type=["csv"])
    if uploaded_draft:
        try:
            st.session_state.field_data = pd.read_csv(uploaded_draft).to_dict('records')
            st.success("Work Resumed!")
        except:
            st.error("Invalid CSV format.")

    with st.form("project_form"):
        c1, c2 = st.columns(2)
        p_name = c1.text_input("Project Name:", value=st.session_state.project_info.get("name", ""))
        p_loc = c1.text_input("Location:", value=st.session_state.project_info.get("loc", ""))
        p_surveyor = c2.text_input("Chief Surveyor:", value=st.session_state.project_info.get("surveyor", ""))
        p_inst = c2.text_input("Instrument ID:", value=st.session_state.project_info.get("inst", ""))
        p_date = st.date_input("Date:", date.today())
        
        if st.form_submit_button("Save Project Details"):
            st.session_state.project_info = {"name": p_name, "loc": p_loc, "surveyor": p_surveyor, "inst": p_inst, "date": p_date}
            st.rerun()

# --- STEP 2: FIELD ENTRY ---
if st.session_state.project_info:
    st.sidebar.header("⚙️ Adjustment Settings")
    k_val = st.sidebar.number_input("Constant k (mm):", value=12.0)
    if st.sidebar.button("🗑️ Reset All Data"):
        st.session_state.field_data = []; st.session_state.project_info = {}; st.rerun()

    st.subheader("📝 Live Entry Form")
    entry_mode = st.radio("Point Type:", ["Starting BM (BS)", "Normal (IS)", "Change Point (FS+BS)", "Closing BM (FS)"], horizontal=True)

    with st.form("field_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st_name = st.text_input("Station:", value=f"S{len(st.session_state.field_data)}")
            int_dist = st.number_input("Interval Dist (m):", min_value=0.0, step=0.1)
        with c2:
            bs = st.number_input("BS (m):", min_value=0.0, step=0.001, format="%.3f") if "BS" in entry_mode else 0.0
            is_val = st.number_input("IS (m):", min_value=0.0, step=0.001, format="%.3f") if "IS" in entry_mode else 0.0
            fs = st.number_input("FS (m):", min_value=0.0, step=0.001, format="%.3f") if "FS" in entry_mode else 0.0
        with c3:
            known_rl = st.number_input("Known RL (m):", min_value=0.0, step=0.001, format="%.3f") if "BM" in entry_mode else 0.0

        if st.form_submit_button("➕ Record Reading"):
            new_row = {'station': st_name, 'interval_dist': int_dist, 'bs': bs if bs > 0 else np.nan, 'is': is_val if is_val > 0 else np.nan, 'fs': fs if fs > 0 else np.nan, 'known_rl': known_rl if known_rl > 0 else np.nan}
            st.session_state.field_data.append(new_row); st.rerun()

    # --- STEP 3: EDITABLE TABLE & CALCULATION ENGINE ---
    if st.session_state.field_data:
        st.divider()
        st.subheader("✍️ Editable Field Book")
        input_df = pd.DataFrame(st.session_state.field_data)
        edited_df = st.data_editor(input_df, num_rows="dynamic", use_container_width=True)
        st.session_state.field_data = edited_df.to_dict('records')

        # --- THE FIX: Robust Calculation Engine ---
        df = edited_df.copy()
        df['cumulative_dist'] = df['interval_dist'].cumsum()
        df['calc_rl'], df['rise'], df['fall'], df['corr'], df['adj_rl'] = [np.nan]*5
        
        # Initialization logic to prevent NameError
        current_rl = 100.000 # Standard Default
        if len(df) > 0 and not pd.isna(df.loc[0, 'known_rl']):
            current_rl = df.loc[0, 'known_rl']
        
        df.loc[0, 'calc_rl'] = current_rl
        prev_staff = df.loc[0, 'bs'] if not pd.isna(df.loc[0, 'bs']) else 0

        # Calculation Loop
        for i in range(1, len(df)):
            curr_reading = df.loc[i, 'is'] if not pd.isna(df.loc[i, 'is']) else df.loc[i, 'fs']
            if not pd.isna(curr_reading):
                diff = prev_staff - curr_reading
                if diff > 0: df.loc[i, 'rise'] = diff
                else: df.loc[i, 'fall'] = abs(diff)
                current_rl += diff
                df.loc[i, 'calc_rl'] = current_rl
                # If there's a new BS at this point (Change Point)
                if not pd.isna(df.loc[i, 'bs']):
                    prev_staff = df.loc[i, 'bs']
                else:
                    prev_staff = curr_reading

        # --- STEP 4: ANALYSIS DASHBOARD ---
        last_idx = len(df) - 1
        final_known = df.loc[last_idx, 'known_rl']
        obt_err, all_err = 0.0, 0.0
        
        if not pd.isna(final_known):
            obt_err = df.loc[last_idx, 'calc_rl'] - final_known
            total_dist_km = df.loc[last_idx, 'cumulative_dist'] / 1000.0
            all_err = (k_val * np.sqrt(total_dist_km)) / 1000.0
            
            # Distance-based Correction
            total_d = df.loc[last_idx, 'cumulative_dist']
            if total_d > 0:
                for i in range(1, len(df)):
                    c = -(obt_err * (df.loc[i, 'cumulative_dist'] / total_d))
                    df.loc[i, 'corr'] = c
                    df.loc[i, 'adj_rl'] = df.loc[i, 'calc_rl'] + c
            df.loc[0, 'adj_rl'] = df.loc[0, 'calc_rl']

        # Formatting Dashboard
        st.subheader("🎯 Live Assessment")
        e1, e2, e3 = st.columns(3)
        e1.metric("Obtained Error", f"{obt_err*1000:.2f} mm")
        e2.metric("Allowable Error", f"±{all_err*1000:.2f} mm")
        st_color = "green" if abs(obt_err) <= all_err else "red"
        e3.markdown(f"Status: **:{st_color}[{'ACCEPTABLE' if st_color=='green' else 'OUT OF LIMIT'}]**")

        st.subheader("📊 Final Analysis & Adjusted Values")
        def format_signed(val):
            if pd.isna(val) or val == 0: return "-"
            return f"{'+' if val > 0 else ''}{val:.4f}"

        st.dataframe(df.style.format({
            'bs': "{:.3f}", 'is': "{:.3f}", 'fs': "{:.3f}", 'rise': "{:.3f}", 'fall': "{:.3f}",
            'calc_rl': "{:.3f}", 'adj_rl': "{:.3f}", 'corr': format_signed
        }), use_container_width=True)

        # --- STEP 5: EXPORTS ---
        st.markdown("---")
        ex1, ex2 = st.columns(2)
        ex1.download_button("💾 Save Progress CSV", df.to_csv(index=False).encode('utf-8'), "Survey_Draft.csv")

        def make_pdf(data, info, err_mm):
            pdf = FPDF(orientation='L')
            pdf.add_page(); pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, f"PROJECT: {info.get('name','N/A')}", ln=True, align='C')
            pdf.set_font("Arial", size=10); pdf.ln(5)
            pdf.cell(0, 7, f"Surveyor: {info.get('surveyor','-')} | Date: {info.get('date','-')}", ln=True)
            pdf.cell(0, 7, f"Misclosure: {err_mm*1000:.2f} mm", ln=True); pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 8)
            h = ["Station", "Cum.Dist", "BS", "IS", "FS", "Rise", "Fall", "Calc RL", "Corr", "Adj RL"]
            w = [25, 20, 25, 25, 25, 25, 25, 30, 25, 30]
            for head, width in zip(h, w): pdf.cell(width, 8, head, 1, 0, 'C')
            pdf.ln()
            pdf.set_font("Arial", size=8)
            for i in range(len(data)):
                row = [str(data.iloc[i]['station']), f"{data.iloc[i]['cumulative_dist']:.1f}", str(data.iloc[i]['bs']), str(data.iloc[i]['is']), str(data.iloc[i]['fs']),
                       str(round(data.iloc[i]['rise'],3)), str(round(data.iloc[i]['fall'],3)), str(round(data.iloc[i]['calc_rl'],3)), format_signed(data.iloc[i]['corr']), str(round(data.iloc[i]['adj_rl'],3))]
                for val, width in zip(row, w): pdf.cell(width, 8, val.replace('nan','-'), 1)
                pdf.ln()
            return pdf.output(dest='S').encode('latin-1', 'ignore')

        try:
            ex2.download_button("📥 Download Final PDF", make_pdf(df, st.session_state.project_info, obt_err), "Survey_Report.pdf")
        except Exception as e:
            ex2.error(f"PDF Error: {e}")