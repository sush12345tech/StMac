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
            sheet_name = f"{key[0]}_{key[1]}_{key[2]}"
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

uploaded_file = st.file_uploader("Upload Data", type=["csv", "xlsx"])

if uploaded_file:
    # Read Data
    data = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)
    
    # Inputs
    with st.sidebar:
        st.header("Settings")
        f_rng = st.slider("Fast EMA", 2, 50, (12, 20))
        s_rng = st.slider("Slow EMA", 10, 100, (26, 40))
        sig_rng = st.slider("Signal EMA", 2, 30, (9, 15))
        target_pct = st.number_input("Target %", 1.0, 50.0, 5.0)
        max_days = st.number_input("Max Days", 1, 100, 10)
        min_trades = st.number_input("Min Trades", 1, 100, 5)
        min_acc = st.number_input("Min Accuracy %", 0, 100, 40)

    # Pre-calculate combinations
    combos = [(f, s, sig) for f in range(f_rng[0], f_rng[1]+1) 
              for s in range(s_rng[0], s_rng[1]+1) 
              for sig in range(sig_rng[0], sig_rng[1]+1) if f < s]
    
    total = len(combos)
    st.info(f"Checking {total} combinations...")

    if st.button("🚀 Start Optimization"):
        results = []
        trades_dict = {}
        
        # Dashboard placeholders
        p_bar = st.progress(0.0)
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        m1 = metric_col1.empty()
        m2 = metric_col2.empty()
        m3 = metric_col3.empty()
        
        best_acc = 0.0
        start_time = time.time()

        for idx, (f, s, sig) in enumerate(combos):
            # FIXED PROGRESS CALCULATION
            # UsingIdx + 1 / total and clipping at 1.0
            prog_val = min(float((idx + 1) / total), 1.0)
            p_bar.progress(prog_val)
            
            # Update Dashboard
            if idx % 5 == 0:
                elapsed = time.time() - start_time
                eta = (elapsed / (idx + 1)) * (total - (idx + 1))
                m1.metric("Checked", f"{idx+1}/{total}")
                m2.metric("Best Accuracy", f"{best_acc}%")
                m3.metric("ETA", f"{int(eta)}s")

            # Logic
            df = data.copy()
            df['m'] = ta.trend.ema_indicator(df.Close, f) - ta.trend.ema_indicator(df.Close, s)
            df['s'] = df['m'].ewm(span=sig).mean()
            df['entry'] = (df['m'].shift(1) < df['s'].shift(1)) & (df['m'] > df['s'])
            
            entries = df[df['entry']].index
            if len(entries) < min_trades: continue
            
            hits = 0
            temp_trades = []
            for e in entries:
                goal = df.loc[e, 'Close'] * (1 + target_pct/100)
                sub = df.loc[e+1 : e+max_days]
                win = sub[sub['Close'] >= goal]
                
                if not win.empty:
                    hits += 1
                    temp_trades.append({"Entry": df.loc[e, 'Date'], "Result": "HIT"})
                else:
                    temp_trades.append({"Entry": df.loc[e, 'Date'], "Result": "MISS"})
            
            acc = round((hits / len(entries)) * 100, 2)
            if acc >= min_acc:
                best_acc = max(best_acc, acc)
                results.append({"Fast": f, "Slow": s, "Signal": sig, "Acc%": acc, "Trades": len(entries)})
                trades_dict[(f, s, sig)] = pd.DataFrame(temp_trades)

        if results:
            res_df = pd.DataFrame(results).sort_values("Acc%", ascending=False)
            st.success("Analysis Complete!")
            st.table(res_df.head(10))
            download_results(res_df.head(10), trades_dict)
        else:
            st.warning("No strategies met the criteria.")
