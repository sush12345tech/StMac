import streamlit as st
import pandas as pd
import numpy as np
from itertools import product
import talib
from io import BytesIO

st.title("MACD Parameter Optimizer")

# ------------------------------
# 1) Upload Data
# ------------------------------
uploaded_file = st.file_uploader("Upload CSV with at least 1500 rows of OHLC data", type=["csv"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    if "Close" not in df.columns:
        st.error("CSV must contain a 'Close' column.")
        st.stop()

    st.success(f"File uploaded successfully! {len(df)} rows loaded.")

    # ------------------------------
    # 2) Input ranges
    # ------------------------------
    st.subheader("Set MACD Parameter Ranges")

    fast_min = st.number_input("Fast EMA (min)", 1, 50, 5)
    fast_max = st.number_input("Fast EMA (max)", 1, 50, 12)

    slow_min = st.number_input("Slow EMA (min)", 5, 100, 20)
    slow_max = st.number_input("Slow EMA (max)", 5, 100, 26)

    signal_min = st.number_input("Signal EMA (min)", 1, 30, 5)
    signal_max = st.number_input("Signal EMA (max)", 1, 30, 9)

    # ------------------------------
    # 3–6) Trading Constraints
    # ------------------------------
    target_pct = st.number_input("Target % from entry", 0.1, 100.0, 5.0)
    max_days = st.number_input("Max days to hit target", 1, 100, 10)
    min_trades = st.number_input("Min number of trades required", 1, 100, 5)
    min_accuracy = st.number_input("Min accuracy %", 1.0, 100.0, 50.0)

    if st.button("Run Optimization"):
        # ------------------------------
        # Generate valid combinations
        # ------------------------------
        fast_range = range(fast_min, fast_max + 1)
        slow_range = range(slow_min, slow_max + 1)
        signal_range = range(signal_min, signal_max + 1)

        param_combos = [(f, s, sig) for f in fast_range
                        for s in slow_range
                        for sig in signal_range
                        if f < s]

        total_combos = len(param_combos)

        st.write(f"Total valid combinations: **{total_combos}**")

        if total_combos > 20000:
            st.error("Too many combinations! Please narrow ranges. Limit = 20,000.")
            st.stop()

        results = []

        close = df["Close"].values

        # ------------------------------
        # Backtesting function
        # ------------------------------
        for fast, slow, sig in param_combos:
            macd, macd_signal, macd_hist = talib.MACD(
                close,
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=sig
            )

            # Signal when MACD crosses above Signal line
            entries = (macd.shift(1) < macd_signal.shift(1)) & (macd > macd_signal)
            entry_indices = np.where(entries)[0]

            wins, total = 0, 0

            for entry_idx in entry_indices:
                entry_price = close[entry_idx]
                target_price = entry_price * (1 + target_pct / 100)

                for j in range(entry_idx + 1, min(entry_idx + max_days + 1, len(close))):
                    if close[j] >= target_price:
                        wins += 1
                        break
                total += 1

            if total >= min_trades:
                accuracy = (wins / total) * 100
                if accuracy >= min_accuracy:
                    results.append({
                        "Fast": fast,
                        "Slow": slow,
                        "Signal": sig,
                        "Trades": total,
                        "Wins": wins,
                        "Accuracy %": round(accuracy, 2)
                    })

        # ------------------------------
        # Show results
        # ------------------------------
        if results:
            results_df = pd.DataFrame(results).sort_values("Accuracy %", ascending=False)
            st.dataframe(results_df.head(10))

            # ------------------------------
            # Download Top 10 to Excel
            # ------------------------------
            top10 = results_df.head(10)
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                top10.to_excel(writer, index=False, sheet_name="Top 10")
            st.download_button(
                label="📥 Download Top 10 Results (Excel)",
                data=output.getvalue(),
                file_name="macd_top10.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No MACD settings met your trade/accuracy requirements.")
