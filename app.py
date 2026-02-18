import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import ta

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
    max_days = st.number_input("Max Trading Days to Hit Target", min_value=1, max_value=len(data), value=10, step=1)
    min_trades = st.number_input("Minimum Trades Required", min_value=1, max_value=100, value=5, step=1)
    min_accuracy = st.number_input("Minimum Accuracy %", min_value=1, max_value=100, value=40, step=1)

    fast_range = range(fast_min, fast_max + 1)
    slow_range = range(slow_min, slow_max + 1)
    signal_range = range(signal_min, signal_max + 1)

    total_combinations = sum(
        len(signal_range)
        for fast in fast_range
        for slow in slow_range
        if fast < slow
    )

    if st.button("🚀 Run Optimization"):

        results = []
        trades_dict = {}
        combos_checked = 0

        progress_bar = st.progress(0)

        for fast in fast_range:
            for slow in slow_range:
                if fast >= slow:
                    continue
                for signal in signal_range:

                    combos_checked += 1
                    progress_bar.progress(min(combos_checked / total_combinations, 1.0))

                    df = data.copy()

                    macd_line = ta.trend.ema_indicator(df["Close"], window=fast) - \
                                ta.trend.ema_indicator(df["Close"], window=slow)

                    signal_line = macd_line.ewm(span=signal).mean()

                    df["MACD"] = macd_line
                    df["Signal"] = signal_line

                    df["Crossover"] = (
                        (df["MACD"].shift(1) < df["Signal"].shift(1)) &
                        (df["MACD"] > df["Signal"])
                    )

                    entries = df[df["Crossover"]].index
                    total_trades = len(entries)

                    if total_trades < min_trades:
                        continue

                    hits = 0
                    trades_records = []
                    above_zero_count = 0

                    for entry in entries:

                        entry_date = df.loc[entry, "Date"]
                        entry_price = df.loc[entry, "Close"]
                        target_price = entry_price * (1 + target_pct / 100)

                        # Determine crossover position
                        if df.loc[entry, "MACD"] > 0 and df.loc[entry, "Signal"] > 0:
                            crossover_position = "Above Zero"
                            above_zero_count += 1
                        else:
                            crossover_position = "Below Zero"

                        last_idx = min(entry + max_days, len(df) - 1)
                        subset = df.loc[entry + 1 : last_idx]

                        exit_price = entry_price
                        exit_date = entry_date
                        hit = False

                        hit_rows = subset[subset["Close"] >= target_price]
                        if not hit_rows.empty:
                            hit = True
                            hits += 1
                            exit_date = hit_rows.iloc[0]["Date"]
                            exit_price = hit_rows.iloc[0]["Close"]
                        elif not subset.empty:
                            exit_date = subset.iloc[-1]["Date"]
                            exit_price = subset.iloc[-1]["Close"]

                        days_held = (exit_date - entry_date).days
                        pct_return = ((exit_price - entry_price) / entry_price) * 100

                        trades_records.append({
                            "Entry Date": entry_date,
                            "Entry Price": entry_price,
                            "Exit Date": exit_date,
                            "Exit Price": exit_price,
                            "Days Held": days_held,
                            "Pct Return": round(pct_return, 2),
                            "Target Hit": hit,
                            "Crossover Position": crossover_position
                        })

                    accuracy = (hits / total_trades) * 100
                    percent_above = (above_zero_count / total_trades) * 100

                    if accuracy >= min_accuracy:

                        trades_df = pd.DataFrame(trades_records)

                        # Add summary row at end
                        summary_row = {
                            "Entry Date": "",
                            "Entry Price": "",
                            "Exit Date": "",
                            "Exit Price": "",
                            "Days Held": "",
                            "Pct Return": "",
                            "Target Hit": "",
                            "Crossover Position": f"% Crossed Above Zero = {round(percent_above,2)}%"
                        }

                        trades_df = pd.concat(
                            [trades_df, pd.DataFrame([summary_row])],
                            ignore_index=True
                        )

                        results.append({
                            "FastEMA": fast,
                            "SlowEMA": slow,
                            "SignalEMA": signal,
                            "Trades": total_trades,
                            "Hits": hits,
                            "Accuracy%": round(accuracy, 2)
                        })

                        trades_dict[(fast, slow, signal)] = trades_df

        if results:

            results_df = pd.DataFrame(results).sort_values(
                "Accuracy%", ascending=False
            ).reset_index(drop=True)

            st.success(f"✅ Found {len(results_df)} valid combinations")

            top10 = results_df.head(10)
            st.dataframe(top10)

            top10_trades_dict = {
                k: v for k, v in trades_dict.items()
                if k in [tuple(x) for x in top10[["FastEMA","SlowEMA","SignalEMA"]].values]
            }

            download_results(top10, top10_trades_dict)

        else:
            st.warning("No parameter combinations matched your criteria.")
