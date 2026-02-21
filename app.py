import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta

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
        file_name="macd_results_with_trades.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ==============================
# App Title
# ==============================
st.title("📈 MACD Parameter Optimizer (Top10 + Trades per Sheet)")
st.markdown("Upload historical price data")

uploaded_file = st.file_uploader(
    "Upload CSV or Excel file (must include 'Date' and 'Close')",
    type=["csv", "xls", "xlsx"]
)

if uploaded_file is not None:
    file_ext = uploaded_file.name.split(".")[-1].lower()
    if file_ext == "csv":
        data = pd.read_csv(uploaded_file)
    elif file_ext in ["xls", "xlsx"]:
        data = pd.read_excel(uploaded_file, engine="openpyxl")
    else:
        st.error("Unsupported file format")
        st.stop()

    if not {"Date", "Close"}.issubset(data.columns):
        st.error("File must contain 'Date' and 'Close' columns.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)

    st.write("### Data Preview")
    st.dataframe(data.head())

    # ==============================
    # Inputs
    # ==============================
    st.markdown("### Enter MACD Parameter Ranges and Optimization Criteria")
    col1, col2, col3 = st.columns(3)
    with col1:
        fast_min = st.number_input("Fast EMA Min", 2, 50, 12)
        fast_max = st.number_input("Fast EMA Max", 2, 50, 20)
    with col2:
        slow_min = st.number_input("Slow EMA Min", 10, 100, 26)
        slow_max = st.number_input("Slow EMA Max", 10, 100, 40)
    with col3:
        signal_min = st.number_input("Signal EMA Min", 2, 30, 9)
        signal_max = st.number_input("Signal EMA Max", 2, 30, 15)

    target_pct = st.number_input("Target % (from entry)", 1.0, 100.0, 5.0)
    max_days = st.number_input("Max Trading Days to Hit Target", 1, len(data), 10)
    min_trades = st.number_input("Minimum Trades Required", 1, 100, 5)
    min_accuracy = st.number_input("Minimum Accuracy %", 1, 100, 40)

    # ==============================
    # Pre-calculate Combinations
    # ==============================
    fast_range = range(fast_min, fast_max + 1)
    slow_range = range(slow_min, slow_max + 1)
    signal_range = range(signal_min, signal_max + 1)

    # Logic to precisely count valid combinations
    valid_combos = []
    for f in fast_range:
        for s in slow_range:
            if f < s:
                for sig in signal_range:
                    valid_combos.append((f, s, sig))
    
    total_combinations = len(valid_combos)

    if total_combinations == 0:
        st.error("Invalid ranges: No combinations where Fast EMA < Slow EMA.")
        st.stop()

    avg_time = 0.05 
    est = total_combinations * avg_time
    st.info(f"⚙️ Combinations to check: {total_combinations:,} | Est. Time: {est:.1f}s")

    # ==============================
    # Run Optimization
    # ==============================
    if st.button("🚀 Run Optimization"):
        results = []
        trades_dict = {}

        progress_bar = st.progress(0.0)
        status_text = st.empty()
        combos_checked = 0

        for fast, slow, signal in valid_combos:
            combos_checked += 1
            
            # UPDATED PROGRESS CALCULATION
            # Ensure value is exactly between 0.0 and 1.0
            current_progress = float(combos_checked / total_combinations)
            progress_bar.progress(min(current_progress, 1.0))
            
            status_text.text(f"Processing: {combos_checked}/{total_combinations}")

            df = data.copy()
            # Technical Analysis
            macd_line = (
                ta.trend.ema_indicator(df["Close"], window=fast)
                - ta.trend.ema_indicator(df["Close"], window=slow)
            )
            signal_line = macd_line.ewm(span=signal).mean()

            df["MACD"] = macd_line
            df["Signal"] = signal_line
            df["Crossover"] = (df["MACD"].shift(1) < df["Signal"].shift(1)) & (df["MACD"] > df["Signal"])

            entries = df[df["Crossover"]].index
            total_trades = len(entries)

            if total_trades < min_trades:
                continue

            hits = 0
            trades_records = []

            for entry in entries:
                entry_date = df.loc[entry, "Date"]
                entry_price = df.loc[entry, "Close"]
                target_price = entry_price * (1 + target_pct / 100)

                last_idx = min(entry + max_days, len(df) - 1)
                subset = df.loc[entry + 1:last_idx]

                if not subset.empty:
                    hit_rows = subset[subset["Close"] >= target_price]
                    if not hit_rows.empty:
                        hits += 1
                        exit_date = hit_rows.iloc[0]["Date"]
                        exit_price = hit_rows.iloc[0]["Close"]
                        hit = True
                    else:
                        exit_date = subset.iloc[-1]["Date"]
                        exit_price = subset.iloc[-1]["Close"]
                        hit = False
                else:
                    exit_date, exit_price, hit = entry_date, entry_price, False

                trades_records.append({
                    "Entry Date": entry_date, "Entry Price": entry_price,
                    "Exit Date": exit_date, "Exit Price": exit_price,
                    "Days Held": (exit_date - entry_date).days,
                    "Pct Return": round(((exit_price - entry_price) / entry_price) * 100, 2),
                    "Target Hit": hit
                })

            accuracy = (hits / total_trades) * 100
            if accuracy >= min_accuracy:
                results.append({
                    "FastEMA": fast, "SlowEMA": slow, "SignalEMA": signal,
                    "Trades": total_trades, "Hits": hits, "Accuracy%": round(accuracy, 2)
                })
                trades_dict[(fast, slow, signal)] = pd.DataFrame(trades_records)

        status_text.text("✅ Optimization Complete!")
        
        if results:
            results_df = pd.DataFrame(results).sort_values("Accuracy%", ascending=False).reset_index(drop=True)
            st.success(f"Found {len(results_df)} valid combinations")
            
            top10 = results_df.head(10)
            st.dataframe(top10)

            top10_keys = [tuple(x) for x in top10[["FastEMA", "SlowEMA", "SignalEMA"]].values]
            top10_trades_dict = {k: v for k, v in trades_dict.items() if k in top10_keys}

            download_results(top10, top10_trades_dict)
        else:
            st.warning("No combinations matched your criteria.")
