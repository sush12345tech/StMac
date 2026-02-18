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

    fast_min = st.number_input("Fast EMA Min", 2, 50, 12)
    fast_max = st.number_input("Fast EMA Max", 2, 50, 20)

    slow_min = st.number_input("Slow EMA Min", 10, 100, 26)
    slow_max = st.number_input("Slow EMA Max", 10, 100, 40)

    signal_min = st.number_input("Signal EMA Min", 2, 30, 9)
    signal_max = st.number_input("Signal EMA Max", 2, 30, 15)

    target_pct = st.number_input("Target %", 1.0, 100.0, 5.0)
    max_days = st.number_input("Max Days", 1, len(data), 10)
    min_trades = st.number_input("Minimum Trades", 1, 100, 5)
    min_accuracy = st.number_input("Minimum Accuracy %", 1, 100, 40)

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
                    above_zero_count = 0
                    above_zero_hits = 0
                    below_zero_hits = 0

                    trades_records = []

                    for entry in entries:

                        entry_date = df.loc[entry, "Date"]
                        entry_price = df.loc[entry, "Close"]
                        target_price = entry_price * (1 + target_pct / 100)

                        if df.loc[entry, "MACD"] > 0 and df.loc[entry, "Signal"] > 0:
                            crossover_position = "Above Zero"
                            above_zero_count += 1
                            is_above = True
                        else:
                            crossover_position = "Below Zero"
                            is_above = False

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

                            if is_above:
                                above_zero_hits += 1
                            else:
                                below_zero_hits += 1

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
                    percent_above_cross = (above_zero_count / total_trades) * 100
                    percent_above_hit_total = (above_zero_hits / total_trades) * 100
                    percent_below_hit_total = (below_zero_hits / total_trades) * 100

                    if accuracy >= min_accuracy:

                        trades_df = pd.DataFrame(trades_records)

                        summary_rows = pd.DataFrame([
                            {"Crossover Position": f"% Crossed Above Zero = {round(percent_above_cross,2)}%"},
                            {"Crossover Position": f"% Target Hit (Above Zero) / Total Trades = {round(percent_above_hit_total,2)}%"},
                            {"Crossover Position": f"% Target Hit (Below Zero) / Total Trades = {round(percent_below_hit_total,2)}%"}
                        ])

                        trades_df = pd.concat([trades_df, summary_rows], ignore_index=True)

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
