"""データ取得モジュール: JPX銘柄リストおよびyfinance価格データの取得"""

import logging
import io

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

logger = logging.getLogger(__name__)

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"


@st.cache_data(ttl=86400, show_spinner="銘柄リストを取得中...")
def fetch_stock_list() -> pd.DataFrame:
    """JPXの公開XLSから東証上場銘柄一覧を取得する。

    Returns:
        コード・銘柄名・市場区分・業種・tickerを含むDataFrame。
        取得失敗時は空のDataFrameを返す。
    """
    try:
        resp = requests.get(JPX_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("JPX銘柄リストのダウンロードに失敗: %s", e)
        return pd.DataFrame()

    try:
        df = pd.read_excel(
            io.BytesIO(resp.content),
            dtype={"コード": str},
        )
    except Exception as e:
        logger.error("JPX XLSのパースに失敗: %s", e)
        return pd.DataFrame()

    # 内国株式のみフィルタ（ETF/REIT等を除外）
    if "市場・商品区分" not in df.columns:
        logger.error("期待する列 '市場・商品区分' がXLSに存在しません")
        return pd.DataFrame()

    df = df[df["市場・商品区分"].str.contains("内国株式", na=False)].copy()

    # 必要列の確認
    required_cols = ["コード", "銘柄名", "市場・商品区分", "33業種区分"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.error("JPX XLSに必要な列がありません: %s", missing)
        return pd.DataFrame()

    df = df[required_cols].copy()
    df["ticker"] = df["コード"].astype(str) + ".T"
    df = df.reset_index(drop=True)

    logger.info("銘柄リスト取得完了: %d銘柄", len(df))
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_price_data(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """yfinanceで個別銘柄の日足データを取得する。

    Args:
        ticker: ティッカーシンボル（例: "7203.T"）
        period: 取得期間（デフォルト: "1y"）

    Returns:
        OHLCV DataFrameまたはNone（取得失敗・データ不足時）
    """
    try:
        df = yf.download(ticker, period=period, progress=False, timeout=10)
    except Exception as e:
        logger.warning("価格データ取得失敗 %s: %s", ticker, e)
        return None

    if df is None or df.empty:
        return None

    # yfinance 0.2.x以降はMultiIndex列を返すことがある
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel("Ticker")

    # NaN行を除去
    df = df.dropna(subset=["Close"])

    if len(df) < 30:
        return None

    return df
