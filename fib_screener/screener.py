"""スクリーニングロジック: スイングポイント検出・フィボナッチ50%計算"""

import numpy as np
import pandas as pd


def detect_swing_points(
    df: pd.DataFrame, window: int = 5
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """スイングハイ・スイングローを検出する。

    前後window本のローソク足と比較し、厳密に最大/最小となる点を検出する。

    Args:
        df: High/Low列を含むDataFrame（reset_index済み）
        window: 前後の比較本数（デフォルト: 5）

    Returns:
        (swing_highs, swing_lows) のタプル。
        各リストは (index, price) タプルのリスト。
    """
    highs = df["High"].values
    lows = df["Low"].values
    n = len(highs)

    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    for i in range(window, n - window):
        # スイングハイ: 前後window本より高値が高い
        is_swing_high = True
        for j in range(1, window + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append((i, float(highs[i])))

        # スイングロー: 前後window本より安値が低い
        is_swing_low = True
        for j in range(1, window + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append((i, float(lows[i])))

    return swing_highs, swing_lows


def find_recent_wave(
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
) -> dict | None:
    """最も直近のスイングハイとスイングローから直近の波を特定する。

    Args:
        swing_highs: (index, price) タプルのリスト
        swing_lows: (index, price) タプルのリスト

    Returns:
        波の情報dict、またはNone（スイングポイント不足時）
    """
    if not swing_highs or not swing_lows:
        return None

    high_idx, high_price = swing_highs[-1]
    low_idx, low_price = swing_lows[-1]

    # 高値が安値以下は無効
    if high_price <= low_price:
        return None

    direction = "上昇波" if low_idx < high_idx else "下降波"

    return {
        "high_price": high_price,
        "low_price": low_price,
        "high_idx": high_idx,
        "low_idx": low_idx,
        "direction": direction,
    }


def calculate_fib_50(wave: dict) -> dict:
    """フィボナッチ50%水準と許容範囲を計算する。

    Args:
        wave: find_recent_waveの戻り値

    Returns:
        fib_50, tolerance_low, tolerance_highを含むdict
    """
    high = wave["high_price"]
    low = wave["low_price"]

    fib_50 = low + (high - low) * 0.5

    return {
        "fib_50": fib_50,
        "tolerance_low": fib_50 * 0.95,
        "tolerance_high": fib_50 * 1.05,
    }


def screen_single_stock(
    df: pd.DataFrame,
    lookback: int = 120,
    tolerance_pct: int = 5,
) -> dict | None:
    """単一銘柄に対してフィボナッチ50%スクリーニングを実行する。

    Args:
        df: 日足OHLCVデータ
        lookback: 分析に使用する直近日数（デフォルト: 120）
        tolerance_pct: 許容乖離率%（デフォルト: 5）

    Returns:
        スクリーニング結果dictまたはNone（条件不一致・データ不足時）
    """
    if len(df) < lookback:
        return None

    # 直近N日に絞る
    recent = df.tail(lookback).copy()
    recent = recent.reset_index(drop=True)

    # スイングポイント検出
    swing_highs, swing_lows = detect_swing_points(recent, window=5)

    # 直近の波を特定
    wave = find_recent_wave(swing_highs, swing_lows)
    if wave is None:
        return None

    # 波の範囲が1%未満はノイズとしてスキップ
    wave_range_pct = (wave["high_price"] - wave["low_price"]) / wave["low_price"]
    if wave_range_pct < 0.01:
        return None

    # フィボナッチ50%計算
    fib_data = calculate_fib_50(wave)

    # 現在値（元のDataFrameの最新終値）
    current_price = float(df["Close"].iloc[-1])

    # 許容範囲を指定%で計算
    tol = tolerance_pct / 100.0
    tolerance_low = fib_data["fib_50"] * (1 - tol)
    tolerance_high = fib_data["fib_50"] * (1 + tol)

    # 範囲外はスキップ
    if not (tolerance_low <= current_price <= tolerance_high):
        return None

    # 乖離率
    deviation_pct = (current_price - fib_data["fib_50"]) / fib_data["fib_50"] * 100

    return {
        "現在値": round(current_price, 1),
        "50%水準": round(fib_data["fib_50"], 1),
        "乖離率": round(deviation_pct, 2),
        "高値": round(wave["high_price"], 1),
        "安値": round(wave["low_price"], 1),
        "波の方向": wave["direction"],
    }
