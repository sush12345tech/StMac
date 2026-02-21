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
            # Limit sheet name length to 31 characters
            sheet_name = sheet_name[:31]
            trades.to_excel(writer, index=False, sheet_name=sheet_name)

    # Verify the output is not empty
    if output.getvalue():
        st.download_button(
            label="📊 Download Excel (Top10 + Trades)",
            data=output.getvalue(),
            file_name="macd_results_with_trades.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.error("No data available for download.")

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
    # ==============================
    # Read File
    # ==============================
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

    fast_min = st.number_input("Fast EMA Min", 2, 50, 12)
    fast_max = st.number_input("Fast EMA Max", 2, 50, 20)

    slow_min = st.number_input("Slow EMA Min", 10, 100, 26)
    slow_max = st.number_input("Slow EMA Max", 10, 100, 40)

    signal_min = st.number_input("Signal EMA Min", 2, 30, 9)
    signal_max = st.number_input("Signal EMA Max", 2, 30, 15)

    target_pct = st.number_input("Target % (from entry)", 1.0, 100.0, 5.0)
    max_days = st.number_input("Max Trading Days to Hit Target", 1, len(data), 10)

    min_trades = st.number_input("Minimum Trades Required", 1, 100, 5)
    min_accuracy = st.number_input("Minimum Accuracy %", 1, 100, 40)

    fast_range = range(fast_min, fast_max + 1)
    slow_range = range(slow_min, slow_max + 1)
    signal_range = range(signal_min, signal_max + 1)

    # ==============================
    # Combination Estimation
    # ==============================
    total_combinations = 0
    for fast in fast_range:
        for slow in slow_range:
            if fast < slow:
                total_combinations += len(signal_range)

    avg_time_per_combination = 0.1
    estimated_seconds = total_combinations * avg_time_per_combination

    st.info(f"⚙️ Approximate combinations to check: {total_combinations:,}")

    # FIX: Prevent division by zero
    if total_combinations == 0:
        st.error("Invalid parameter ranges: Fast EMA must be less than Slow EMA.")
        st.stop()

    if estimated_seconds < 60:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds:.1f} seconds")
    elif estimated_seconds < 3600:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds/60:.1f} minutes")
    else:
        st.info(f"⏳ Estimated analysis time: {estimated_seconds/3600:.2f} hours")

    # ==============================
    # Run Optimization
    # ==============================
    if st.button("🚀 Run Optimization"):

        results = []
        trades_dict = {}

        # Initialize progress bar
        progress_bar = st.progress(0.0)
        combo_checked_text = st.empty()
        combo_remaining_text = st.empty()

        combos_checked = 0

        # Wrap entire loop with spinner for better UX
        with st.spinner("Processing parameter combinations..."):
            try:
                for fast in fast_range:
                    for slow in slow_range:
                        if fast >= slow:
                            continue
                        for signal in signal_range:
                            combos_checked += 1

                            # Calculate progress
                            if total_combinations > 0:
                                progress_value = float(combos_checked) / float(total_combinations)
                            else:
                                progress_value = 0.0
                            # Clamp to [0.0, 1.0]
                            progress_value = max(0.0, min(progress_value, 1.0))
                            progress_bar.progress(progress_value)

                            # Update text info
                            combo_checked_text.text(f"✅ Combinations checked: {combos_checked:,}")
                            combo_remaining_text.text(f"⌛ Combinations remaining: {total_combinations - combos_checked:,}")

                            # Slight delay for UI responsiveness
                            time.sleep(0.001)

                            # MACD Calculation
                            df = data.copy()

                            macd_line = (
                                ta.trend.ema_indicator(df["Close"], window=fast)
                                - ta.trend.ema_indicator(df["Close"], window=slow)
                            )
                            signal_line = macd_line.ewm(span=signal).mean()

                            df["MACD"] = macd_line
                            df["Signal"] = signal_line

                            df["Crossover"] = (
                                (df["MACD"].shift(1) < df["Signal"].shift(1))
                                & (df["MACD"] > df["Signal"])
                            )

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

                                hit = False
                                hit_rows = subset[subset["Close"] >= target_price]

                                if not hit_rows.empty:
                                    hit = True
                                    hits += 1
                                    exit_date = hit_rows.iloc[0]["Date"]
                                    exit_price = hit_rows.iloc[0]["Close"]
                                else:
                                    if not subset.empty:
                                        exit_date = subset.iloc[-1]["Date"]
                                        exit_price = subset.iloc[-1]["Close"]
                                    else:
                                        exit_date = entry_date
                                        exit_price = entry_price

                                days_held = (exit_date - entry_date).days
                                pct_return = ((exit_price - entry_price) / entry_price) * 100

                                trades_records.append({
                                    "Entry Date": entry_date,
                                    "Entry Price": entry_price,
                                    "Exit Date": exit_date,
                                    "Exit Price": exit_price,
                                    "Days Held": days_held,
                                    "Pct Return": round(pct_return, 2),
                                    "Target Hit": hit
                                })

                            accuracy = (hits / total_trades) * 100

                            if accuracy >= min_accuracy:
                                results.append({
                                    "FastEMA": fast,
                                    "SlowEMA": slow,
                                    "SignalEMA": signal,
                                    "Trades": total_trades,
                                    "Hits": hits,
                                    "Accuracy%": round(accuracy, 2)
                                })

                                trades_dict[(fast, slow, signal)] = pd.DataFrame(trades_records)

                # End of nested loops
                progress_bar.progress(1.0)
                combo_checked_text.text(f"✅ Combinations checked: {total_combinations:,}")
                combo_remaining_text.text("⌛ Combinations remaining: 0")
            except Exception as e:
                st.error(f"An error occurred: {e}")

        # Display results
        if results:
            results_df = (
                pd.DataFrame(results)
                .sort_values("Accuracy%", ascending=False)
                .reset_index(drop=True)
            )

            st.success(f"✅ Found {len(results_df)} valid combinations")

            st.write("### Top 10 Results")
            top10 = results_df.head(10)
            st.dataframe(top10)

            top10_keys = [
                tuple(x) for x in top10[["FastEMA", "SlowEMA", "SignalEMA"]].values
            ]

            top10_trades_dict = {
                k: v for k, v in trades_dict.items() if k in top10_keys
            }

            # Download if data exists
            if top10_trades_dict:
                download_results(top10, top10_trades_dict)
            else:
                st.warning("No trades data for top results.")
        else:
            st.warning("No parameter combinations matched your criteria.")
