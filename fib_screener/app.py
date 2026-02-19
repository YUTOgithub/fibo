"""TSE フィボナッチ50%リトレースメント スクリーナー - Streamlitメインアプリ"""

import logging
import time
from datetime import date

import pandas as pd
import streamlit as st

from data_fetcher import fetch_stock_list, fetch_price_data
from screener import screen_single_stock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="TSE フィボナッチ スクリーナー",
    layout="wide",
)

st.title("TSE フィボナッチ50%リトレースメント スクリーナー")

# --- 銘柄リスト取得 ---
stock_list = fetch_stock_list()

if stock_list.empty:
    st.error("銘柄リストの取得に失敗しました。JPXのサイトに接続できない可能性があります。")
    st.stop()

# --- サイドバー ---
st.sidebar.header("スクリーニング条件")

available_markets = sorted(stock_list["市場・商品区分"].unique().tolist())
selected_markets = st.sidebar.multiselect(
    "市場区分",
    options=available_markets,
    default=available_markets,
)

available_industries = sorted(stock_list["33業種区分"].dropna().unique().tolist())
selected_industries = st.sidebar.multiselect(
    "業種（空の場合は全業種）",
    options=available_industries,
    default=[],
)

lookback = st.sidebar.slider("分析期間（日数）", 60, 180, 120)
tolerance = st.sidebar.slider("許容乖離率（%）", 1, 10, 5)

# フィルタ適用
filtered = stock_list[stock_list["市場・商品区分"].isin(selected_markets)]
if selected_industries:
    filtered = filtered[filtered["33業種区分"].isin(selected_industries)]

st.sidebar.metric("対象銘柄数", len(filtered))

# --- 説明 ---
with st.expander("スクリーニング方法について"):
    st.markdown(f"""
- 過去 **{lookback}日間** の日足データからスイングハイ・スイングローを検出（前後5本比較）
- 直近のスイングハイとスイングローのペア（直近の波）を特定
- **フィボナッチ50%水準**（安値 +（高値 - 安値）× 0.5）を算出
- 現在の終値が50%水準の **±{tolerance}%以内** にある銘柄を抽出
    """)

# --- スクリーニング実行 ---
run_button = st.sidebar.button("スクリーニング開始", type="primary")

if run_button:
    tickers = filtered["ticker"].tolist()
    codes = filtered["コード"].tolist()
    names = filtered["銘柄名"].tolist()

    results: list[dict] = []
    errors: list[str] = []

    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(tickers)

    for i, (ticker, code, name) in enumerate(zip(tickers, codes, names)):
        status_text.text(f"処理中: {code} {name} ({i + 1}/{total})")
        progress_bar.progress((i + 1) / total)

        try:
            df = fetch_price_data(ticker)
            if df is None:
                continue

            result = screen_single_stock(
                df, lookback=lookback, tolerance_pct=tolerance
            )
            if result is not None:
                result["証券コード"] = code
                result["銘柄名"] = name
                results.append(result)
        except Exception as e:
            errors.append(f"{code} {name}: {e}")
            logger.warning("スクリーニングエラー %s: %s", ticker, e)

        time.sleep(0.1)

    progress_bar.empty()
    status_text.empty()

    # session_stateに保存
    st.session_state["results"] = results
    st.session_state["errors"] = errors
    st.session_state["total"] = total

# --- 結果表示 ---
if "results" in st.session_state:
    results = st.session_state["results"]
    errors = st.session_state["errors"]
    total = st.session_state["total"]

    col1, col2 = st.columns(2)
    col1.metric("対象銘柄数", total)
    col2.metric("該当銘柄数", len(results))

    if results:
        result_df = pd.DataFrame(results)
        column_order = [
            "証券コード", "銘柄名", "現在値", "50%水準",
            "乖離率", "高値", "安値", "波の方向",
        ]
        result_df = result_df[column_order]
        result_df = result_df.sort_values("乖離率", key=abs)

        st.dataframe(result_df, use_container_width=True, hide_index=True)

        csv = result_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="CSVダウンロード",
            data=csv,
            file_name=f"fib50_screener_{date.today().isoformat()}.csv",
            mime="text/csv",
        )
    else:
        st.warning("該当する銘柄が見つかりませんでした。")

    if errors:
        with st.expander(f"エラー（{len(errors)}件）"):
            for err in errors:
                st.text(err)
