import streamlit as st
import pandas as pd
import numpy as np
import ta
from itertools import product
from io import BytesIO

st.title("MACD Parameter Optimizer")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:

    data = pd.read_excel(uploaded_file)

    st.write("### Data Preview")
    st.dataframe(data.head())

    stock_name = st.text_input("Enter Stock Name", "SampleStock")

    fast_range = range(5, 21)
    slow_range = range(20, 61)
    signal_range = range(5, 16)

    total_combinations = len(fast_range) * len(slow_range) * len(signal_range)

    st.write(f"⚙️ Approximate combinations to check: **{total_combinations:,}**")

    if st.button("🚀 Run Optimization"):

        results = []
        trades_dict = {}

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

                    # Update UI every 25 iterations (prevents UI freezing)
                    if combos_checked % 25 == 0:

                        progress_value = min(combos_checked / total_combinations, 1.0)

                        progress_bar.progress(progress_value)

                        combo_checked_text.text(
                            f"✅ Combinations checked: {combos_checked:,}"
                        )

                        combo_remaining_text.text(
                            f"⌛ Combinations remaining: {total_combinations - combos_checked:,}"
                        )

                    df = data.copy()

                    macd_line = (
                        ta.trend.ema_indicator(df["Close"], window=fast)
                        - ta.trend.ema_indicator(df["Close"], window=slow)
                    )

                    signal_line = ta.trend.ema_indicator(macd_line, window=signal)

                    df["MACD"] = macd_line
                    df["Signal"] = signal_line

                    df["Cross"] = (df["MACD"] > df["Signal"]) & (
                        df["MACD"].shift(1) <= df["Signal"].shift(1)
                    )

                    trades = df[df["Cross"]]

                    total_trades = len(trades)

                    hits = 0
                    trade_records = []

                    for idx in trades.index:

                        entry_price = df.loc[idx, "Close"]
                        entry_date = df.loc[idx, "Date"]

                        future = df.loc[idx+1:idx+5]

                        if future.empty:
                            continue

                        exit_price = future["Close"].iloc[-1]
                        exit_date = future["Date"].iloc[-1]

                        pct_return = ((exit_price - entry_price) / entry_price) * 100

                        hit = pct_return > 0

                        if hit:
                            hits += 1

                        trade_records.append({
                            "Stock": stock_name,
                            "Entry Date": entry_date,
                            "Entry Price": entry_price,
                            "Exit Date": exit_date,
                            "Exit Price": exit_price,
                            "Pct Return": round(pct_return,2),
                            "Target Hit": hit
                        })

                    if total_trades > 0:

                        accuracy = (hits / total_trades) * 100

                        results.append({
                            "Stock": stock_name,
                            "FastEMA": fast,
                            "SlowEMA": slow,
                            "SignalEMA": signal,
                            "Trades": total_trades,
                            "Hits": hits,
                            "Accuracy%": round(accuracy,2)
                        })

                        trades_dict[f"{fast}_{slow}_{signal}"] = pd.DataFrame(trade_records)

        # Final progress update
        progress_bar.progress(1.0)

        combo_checked_text.text(
            f"✅ Combinations checked: {total_combinations:,}"
        )

        combo_remaining_text.text(
            "⌛ Combinations remaining: 0"
        )

        results_df = pd.DataFrame(results)

        top10 = results_df.sort_values("Accuracy%", ascending=False).head(10)

        st.write("### Top 10 Results")
        st.dataframe(top10)

        output = BytesIO()

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

            top10.to_excel(writer, sheet_name="Top10 Results", index=False)

            for key, df_trades in trades_dict.items():

                df_trades.to_excel(writer, sheet_name=key[:31], index=False)

        st.download_button(
            label="Download Excel Results",
            data=output.getvalue(),
            file_name=f"{stock_name}_MACD_Optimization.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
