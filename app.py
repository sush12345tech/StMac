import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta

def download_results(df):
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Top 10 Results (CSV)",
        data=csv,
        file_name="top10_macd_results.csv",
        mime="text/csv",
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Top10 Results")
    st.download_button(
        label="📊 Download Top 10 Results (Excel)",
        data=output.getvalue(),
        file_name="top10_macd_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.title("📈 MACD Parameter Optimizer without max days restriction")

st.markdown("""
Upload historical price data (1500+ days recommended)  
and test MACD parameter combinations to find the most accurate ones
based on your target conditions.
""")

uploaded_file = st.file_uploader("Upload CSV or Excel file (must include 'Date' and 'Close')", type=["csv", "xls", "xlsx"])

if uploaded_file is not None:
    file_ext = uploaded_file.name.split(".")[-1].lower()
    if file_ext == "csv":
        data = pd.read_csv(uploaded_file)
    elif file_ext in ["xls", "xlsx"]:
        data = pd.read_excel(uploaded_file, engine="openpyxl")
    else:
        st.error("Unsupported file format")
        st.stop()

    if not set(["Date", "Close"]).issubset(data.columns):
        st.error("File must contain 'Date' and 'Close' columns.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)

    st.write("### Data Preview", data.head())

    st.markdown("### Enter MACD Parameter Ranges and Optimization Criteria")

    fast_min = st.number_input("Fast EMA Min", min_value=2, max_value=50, value=12, step=1)
    fast_max = st.number_input("Fast EMA Max", min_value=2, max_value=50, value=20, step=1)

    slow_min = st.number_input("Slow EMA Min", min_value=10, max_value=100, value=26, step=1)
    slow_max = st.number_input("Slow EMA Max", min_value=10, max_value=100, value=40, step=1)

    signal_min = st.number_input("Signal EMA Min", min_value=2, max_value=30, value=9, step=1)
    signal_max = st.number_input("Signal EMA Max", min_value=2, max_value=30, value=15, step=1)

    target_pct = st.number_input("Target % (from entry)", min_value=1.0, max_value=100.0, value=5.0, step=0.1)

    # Removed 100 cap; max_days max_value set to data length
    max_days = st.number_input("Max Trading Days to Hit Target", min_value=1, max_value=len(data), value=10, step=1)

    min_trades = st.number_input("Minimum Trades Required", min_value=1, max_value=100, value=5, step=1)

    min_accuracy = st.number_input("Minimum Accuracy %", min_value=1, max_value=100, value=40, step=1)

    fast_range = range(fast_min, fast_max + 1)
    slow_range = range(slow_min, slow_max + 1)
    signal_range = range(signal_min, signal_max + 1)

    total_combinations = 0
    for fast in fast_range:
        for slow in slow_range:
            if fast < slow:
                total_combinations += len(signal_range)

    avg_time_per_combination = 0.1
    estimated_seconds = total_combinations * avg_time_per_combination

    st.info(f"⚙️ Approximate combinations to check: {total_combinations:,}")
    if estimated_seconds < 60:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds:.1f} seconds")
    elif estimated_seconds < 3600:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds / 60:.1f} minutes")
    else:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds / 3600:.2f} hours")

    if st.button("🚀 Run Optimization"):
        results = []

        progress_bar = st.progress(0)
        combo_checked_text = st.empty()
        combo_remaining_text = st.empty()

        combos_checked = 0

        for fast in fast_range:
            for slow in slow_range:
                if fast >= slow:
                    continue
                for signal in signal_range:
                    combos_checked += 1
                    progress_bar.progress(min(combos_checked / total_combinations, 1.0))
                    combo_checked_text.text(f"✅ Combinations checked: {combos_checked:,}")
                    combo_remaining_text.text(f"⌛ Combinations remaining: {total_combinations - combos_checked:,}")

                    df = data.copy()

                    macd_line = ta.trend.ema_indicator(df["Close"], window=fast) - ta.trend.ema_indicator(df["Close"], window=slow)
                    signal_line = macd_line.ewm(span=signal).mean()

                    df["MACD"] = macd_line
                    df["Signal"] = signal_line

                    df["Crossover"] = (df["MACD"].shift(1) < df["Signal"].shift(1)) & (df["MACD"] > df["Signal"])

                    entries = df[df["Crossover"]].index
                    total_trades = len(entries)

                    if total_trades < min_trades:
                        continue

                    hits = 0
                    for entry in entries:
                        entry_price = df.loc[entry, "Close"]
                        target_price = entry_price * (1 + target_pct / 100)

                        # Limit search to max_days after entry (prevent overshoot)
                        last_idx = min(entry + max_days, len(df) - 1)
                        subset = df.loc[entry + 1 : last_idx]

                        if (subset["Close"] >= target_price).any():
                            hits += 1

                    accuracy = (hits / total_trades) * 100 if total_trades > 0 else 0

                    if accuracy >= min_accuracy:
                        results.append({
                            "FastEMA": fast,
                            "SlowEMA": slow,
                            "SignalEMA": signal,
                            "Trades": total_trades,
                            "Hits": hits,
                            "Accuracy%": round(accuracy, 2)
                        })

        progress_bar.progress(1.0)
        combo_checked_text.text(f"✅ Combinations checked: {total_combinations:,}")
        combo_remaining_text.text(f"⌛ Combinations remaining: 0")

        if results:
            results_df = pd.DataFrame(results).sort_values("Accuracy%", ascending=False).reset_index(drop=True)
            st.success(f"✅ Found {len(results_df)} valid combinations")
            st.write("### Top 10 Results")
            top10 = results_df.head(10)
            st.dataframe(top10)
            download_results(top10)
        else:
            st.warning("No parameter combinations matched your criteria.")
