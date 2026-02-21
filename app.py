import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta
import time

# ==============================
# Excel Download Function
# ==============================
def download_results(df, trades_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Top10 Results")
        for key, trades in trades_dict.items():
            # Create a safe sheet name
            sheet_name = f"F{key[0]}_S{key[1]}_G{key[2]}"
            trades.to_excel(writer, index=False, sheet_name=sheet_name[:31])

    st.download_button(
        label="📊 Download Excel (Top10 + Trades)",
        data=output.getvalue(),
        file_name="macd_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ==============================
# UI Setup
# ==============================
st.set_page_config(page_title="MACD Optimizer", layout="wide")
st.title("📈 MACD Parameter Optimizer")

uploaded_file = st.file_uploader("Upload Data (CSV or XLSX)", type=["csv", "xlsx"])

if uploaded_file:
    # Read Data
    try:
        data = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
        data["Date"] = pd.to_datetime(data["Date"])
        data = data.sort_values("Date").reset_index(drop=True)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        st.stop()
    
    # Settings Sidebar
    with st.sidebar:
        st.header("Optimization Settings")
        f_min, f_max = st.slider("Fast EMA Range", 2, 50, (12, 20))
        s_min, s_max = st.slider("Slow EMA Range", 10, 100, (26, 40))
        sig_min, sig_max = st.slider("Signal EMA Range", 2, 30, (9, 15))
        
        st.divider()
        target_pct = st.number_input("Target Profit %", 0.5, 50.0, 5.0)
        max_days = st.number_input("Max Holding Days", 1, 200, 10)
        min_trades = st.number_input("Min Trades Required", 1, 100, 5)
        min_acc = st.number_input("Min Accuracy % Goal", 0, 100, 40)

    # Pre-calculate combinations
    combos = [(f, s, sig) for f in range(f_min, f_max+1) 
              for s in range(s_min, s_max+1) 
              for sig in range(sig_min, sig_max+1) if f < s]
    
    total = len(combos)
    if total == 0:
        st.warning("No valid combinations (Fast must be < Slow). Adjust ranges.")
        st.stop()

    st.info(f"Total combinations to check: {total}")

    if st.button("🚀 Run Optimization"):
        results = []
        trades_dict = {}
        
        # Display elements
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        m_col1, m_col2, m_col3 = st.columns(3)
        m1 = m_col1.empty()
        m2 = m_col2.empty()
        m3 = m_col3.empty()
        
        best_acc = 0.0
        start_time = time.time()

        for idx, (f, s, sig) in enumerate(combos):
            # FIXED PROGRESS CALCULATION: Explicitly clip between 0.0 and 1.0
            current_idx = idx + 1
            raw_progress = current_idx / total
            clamped_progress = max(0.0, min(float(raw_progress), 1.0))
            progress_bar.progress(clamped_progress)
            
            # UI Updates (Every 10 iterations to save resources)
            if current_idx % 10 == 0 or current_idx == total:
                elapsed = time.time() - start_time
                per_iter = elapsed / current_idx
                eta = per_iter * (total - current_idx)
                
                m1.metric("Checked", f"{current_idx}/{total}")
                m2.metric("Best Accuracy", f"{best_acc}%")
                m3.metric("ETA", f"{int(eta)}s" if eta > 0 else "Finishing...")
                status_text.text(f"Current Params: Fast={f}, Slow={s}, Signal={sig}")

            # MACD Calculation
            df = data.copy()
            fast_ema = df['Close'].ewm(span=f, adjust=False).mean()
            slow_ema = df['Close'].ewm(span=s, adjust=False).mean()
            macd_line = fast_ema - slow_ema
            signal_line = macd_line.ewm(span=sig, adjust=False).mean()
            
            # Entry Signal (Crossover)
            entry_signal = (macd_line.shift(1) < signal_line.shift(1)) & (macd_line > signal_line)
            entries = df[entry_signal].index
            
            if len(entries) < min_trades:
                continue
            
            hits = 0
            temp_trades = []
            for e in entries:
                entry_price = df.loc[e, 'Close']
                target_price = entry_price * (1 + target_pct/100)
                
                # Look forward max_days
                subset = df.loc[e+1 : e+max_days]
                win_condition = subset[subset['Close'] >= target_price]
                
                if not win_condition.empty:
                    hits += 1
                    exit_date = win_condition.iloc[0]['Date']
                    temp_trades.append({"Entry Date": df.loc[e, 'Date'], "Status": "HIT", "Exit Date": exit_date})
                else:
                    temp_trades.append({"Entry Date": df.loc[e, 'Date'], "Status": "MISS", "Exit Date": "N/A"})
            
            acc = round((hits / len(entries)) * 100, 2)
            if acc >= min_acc:
                if acc > best_acc:
                    best_acc = acc
                results.append({"Fast": f, "Slow": s, "Signal": sig, "Accuracy %": acc, "Total Trades": len(entries)})
                trades_dict[(f, s, sig)] = pd.DataFrame(temp_trades)

        # Final Display logic (outside the loop)
        progress_bar.empty()
        status_text.success("✅ Optimization Complete!")
        
        if results:
            final_df = pd.DataFrame(results).sort_values("Accuracy %", ascending=False).reset_index(drop=True)
            top_10 = final_df.head(10)
            
            st.subheader("Top 10 Parameter Sets")
            st.dataframe(top_10, use_container_width=True)
            
            # Filtering trade dictionary to only include Top 10 for Excel size
            top_keys = [tuple(x) for x in top_10[["Fast", "Slow", "Signal"]].values]
            final_trades = {k: v for k, v in trades_dict.items() if k in top_keys}
            
            download_results(top_10, final_trades)
        else:
            st.error("No parameter combinations met your minimum requirements. Try lowering 'Min Accuracy' or 'Min Trades'.")
