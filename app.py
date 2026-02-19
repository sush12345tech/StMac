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
    else:
        data = pd.read_excel(uploaded_file, engine="openpyxl")

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

    if st.button("🚀 Run Optimization"):

        results = []
        trades_dict = {}

        for fast in fast_range:
            for slow in slow_range:
                if fast >= slow:
                    continue
                for signal in signal_range:

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

                    hits = 0
                    above_zero_count = 0
                    below_zero_count = 0
                    above_zero_hits = 0
                    below_zero_hits = 0

                    trades_records = []

                    for i, entry in enumerate(entries):

                        entry_date = df.loc[entry, "Date"]
                        entry_price = df.loc[entry, "Close"]
                        target_price = entry_price * (1 + target_pct / 100)

                        if df.loc[entry, "MACD"] > 0 and df.loc[entry, "Signal"] > 0:
                            crossover_position = "Above Zero"
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

                    # --------- REMOVE LAST TRADE IF TARGET HIT = FALSE ----------
                    if trades_records:
                        if trades_records[-1]["Target Hit"] is False:
                            trades_records = trades_records[:-1]

                    total_trades = len(trades_records)

                    if total_trades < min_trades:
                        continue

                    for trade in trades_records:
                        if trade["Crossover Position"] == "Above Zero":
                            above_zero_count += 1
                            if trade["Target Hit"]:
                                above_zero_hits += 1
                                hits += 1
                        else:
                            below_zero_count += 1
                            if trade["Target Hit"]:
                                below_zero_hits += 1
                                hits += 1

                    accuracy = (hits / total_trades) * 100 if total_trades > 0 else 0

                    if accuracy >= min_accuracy:

                        percent_above_cross = (above_zero_count / total_trades) * 100
                        percent_above_hit_total = (above_zero
