# ============================================================
# B3_INVESTMENT_ENGINE
# build_technical_prices.py
#
# CAMADA TÉCNICA LIVE
#
# OBJETIVO:
#
# Em cada execução:
#
# B3 atual
#   ↓
# OHLC
#   ↓
# neutralização mecânica de eventos corporativos
#   ↓
# isolamento de descontinuidades residuais
#   ↓
# segmentação técnica
#   ↓
# cálculo dos 7 indicadores congelados
#   ↓
# technical_prices_live.csv
#
# METODOLOGIA PRESERVADA:
#
# - NÃO cria Technical Score
# - NÃO cria sinal de compra/venda
# - NÃO cria gatilho obrigatório
# - NÃO refaz pesquisa OOS
# - NÃO altera Quality
# - NÃO altera Valuation
# - NÃO participa do ranking fundamental
# - NÃO recupera empresa reprovada
#
# Os dados avançam no tempo.
# A metodologia permanece congelada.
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd


# ============================================================
# 1. DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

LIVE_DIR = DATA_DIR / "live"

B3_DIR = LIVE_DIR / "b3"

FUNDAMENTAL_DIR = LIVE_DIR / "fundamental"

PROCESSED_DIR = LIVE_DIR / "processed"

TECHNICAL_DIR = LIVE_DIR / "technical"

TECHNICAL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. ENTRADAS
# ============================================================

MARKET_HISTORY_FILE = (
    B3_DIR
    / "market_history_live.csv"
)

SPRE_PRICES_FILE = (
    B3_DIR
    / "spre_prices_live.csv"
)

FUNDAMENTAL_INPUT_FILE = (
    FUNDAMENTAL_DIR
    / "fundamental_input_live.csv"
)

FCA_SECURITY_HISTORY_FILE = (
    PROCESSED_DIR
    / "fca_security_history.csv"
)


# ============================================================
# 3. SAÍDAS
# ============================================================

OUTPUT_FILE = (
    TECHNICAL_DIR
    / "technical_prices_live.csv"
)

MANIFEST_FILE = (
    TECHNICAL_DIR
    / "technical_prices_live_manifest.json"
)

CORPORATE_ACTION_FILE = (
    TECHNICAL_DIR
    / "technical_corporate_actions_live.csv"
)

RESIDUAL_FILE = (
    TECHNICAL_DIR
    / "technical_residual_discontinuities_live.csv"
)


# ============================================================
# 4. METODOLOGIA CONGELADA — CELL05B
# ============================================================

ACTION_RATIOS = np.array(
    [
        0.10,
        0.125,
        0.20,
        0.25,
        1 / 3,
        0.40,
        0.50,
        2 / 3,
        0.75,
        1.50,
        2.00,
        2.50,
        3.00,
        4.00,
        5.00,
        8.00,
        10.00,
    ],
    dtype=float,
)

MIN_ABS_MOVE = 0.30
MAX_RELATIVE_ERROR = 0.02


# ============================================================
# 5. METODOLOGIA CONGELADA — CELL06B
# ============================================================

RESIDUAL_RETURN_LIMIT = 0.80


# ============================================================
# 6. INDICADORES FINAIS CONGELADOS
# ============================================================

TECHNICAL_INDICATORS = [
    "SMA200_SLOPE_20D",
    "ATR_PCT",
    "ROC_60",
    "MACD_HIST_PCT",
    "DIST_SMA_200",
    "BB_WIDTH",
    "DIST_SMA_50",
]


# ============================================================
# 7. COLUNAS DE SAÍDA
# ============================================================

IDENTITY_COLUMNS = [
    "CD_CVM",
    "TICKER",
    "DATE",
    "TECH_SEGMENT_ID",
]

PRICE_COLUMNS = [
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
]

OUTPUT_COLUMNS = (
    IDENTITY_COLUMNS
    + PRICE_COLUMNS
    + TECHNICAL_INDICATORS
)


# ============================================================
# 8. NORMALIZAR COLUNAS
# ============================================================

def normalize_columns(df):

    result = df.copy()

    result.columns = [
        str(column).strip().upper()
        for column in result.columns
    ]

    return result


# ============================================================
# 9. LOCALIZAR COLUNA
# ============================================================

def find_column(df, candidates, required=True):

    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    if required:
        raise ValueError(
            "Nenhuma coluna compatível encontrada. "
            f"Esperadas: {candidates}"
        )

    return None


# ============================================================
# 10. PADRONIZAR BASE DE PREÇOS
# ============================================================

def normalize_price_source(df, source_name):

    df = normalize_columns(df)

    ticker_col = find_column(
        df,
        [
            "TICKER",
            "CODNEG",
            "COD_NEGOCIACAO",
            "CODIGO_NEGOCIACAO",
            "SYMBOL",
        ],
    )

    date_col = find_column(
        df,
        [
            "DATA",
            "DATE",
            "DATPRE",
            "TRADE_DATE",
            "TRADDT",
        ],
    )

    open_col = find_column(
        df,
        [
            "OPEN",
            "PREABE",
            "OPEN_PRICE",
            "PRCOPEN",
            "FIRST_PRICE",
        ],
    )

    high_col = find_column(
        df,
        [
            "HIGH",
            "PREMAX",
            "HIGH_PRICE",
            "PRCHIGH",
        ],
    )

    low_col = find_column(
        df,
        [
            "LOW",
            "PREMIN",
            "LOW_PRICE",
            "PRCLOW",
        ],
    )

    close_col = find_column(
        df,
        [
            "CLOSE",
            "PREULT",
            "CLOSE_PRICE",
            "PRCCLOSE",
            "LAST_PRICE",
        ],
    )

    result = df[
        [
            ticker_col,
            date_col,
            open_col,
            high_col,
            low_col,
            close_col,
        ]
    ].copy()

    result.columns = [
        "TICKER",
        "DATE",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]

    result["TICKER"] = (
        result["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["DATE"] = pd.to_datetime(
        result["DATE"],
        errors="coerce",
    )

    for column in PRICE_COLUMNS:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=[
            "TICKER",
            "DATE",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
        ]
    )

    result = result[
        (result["OPEN"] > 0)
        & (result["HIGH"] > 0)
        & (result["LOW"] > 0)
        & (result["CLOSE"] > 0)
    ]

    result = result[
        result["HIGH"]
        >= result[
            ["OPEN", "LOW", "CLOSE"]
        ].max(axis=1)
    ]

    result = result[
        result["LOW"]
        <= result[
            ["OPEN", "HIGH", "CLOSE"]
        ].min(axis=1)
    ]

    result["SOURCE"] = source_name

    return result


# ============================================================
# 11. CARREGAR HISTÓRICO B3
# ============================================================

def load_market_history():

    if not MARKET_HISTORY_FILE.exists():
        raise FileNotFoundError(
            "\nBase histórica B3 LIVE não encontrada:\n"
            f"{MARKET_HISTORY_FILE}\n\n"
            "Execute primeiro build_b3_market_history.py."
        )

    print("\n" + "=" * 80)
    print("CARREGANDO HISTÓRICO B3")
    print("=" * 80)

    raw = pd.read_csv(
        MARKET_HISTORY_FILE,
        low_memory=False,
    )

    history = normalize_price_source(
        raw,
        "B3_COTAHIST",
    )

    print("Registros históricos:", len(history))
    print("Primeira data:", history["DATE"].min())
    print("Última data:", history["DATE"].max())

    return history


# ============================================================
# 12. CARREGAR PREÇOS B3 DO ANO CORRENTE
# ============================================================

def load_current_year_prices():

    if not SPRE_PRICES_FILE.exists():

        print(
            "\nATENÇÃO: spre_prices_live.csv "
            "não encontrado."
        )

        return pd.DataFrame(
            columns=[
                "TICKER",
                "DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "SOURCE",
            ]
        )

    print("\n" + "=" * 80)
    print("CARREGANDO PREÇOS B3 DO ANO CORRENTE")
    print("=" * 80)

    raw = pd.read_csv(
        SPRE_PRICES_FILE,
        low_memory=False,
    )

    current = normalize_price_source(
        raw,
        "B3_SPRE",
    )

    print("Registros ano corrente:", len(current))

    if not current.empty:
        print("Primeira data:", current["DATE"].min())
        print("Última data:", current["DATE"].max())

    return current


# ============================================================
# 13. CONSOLIDAR PREÇOS
# ============================================================

def build_price_history():

    history = load_market_history()
    current = load_current_year_prices()

    frames = [history]

    if not current.empty:
        frames.append(current)

    prices = pd.concat(
        frames,
        ignore_index=True,
    )

    source_priority = {
        "B3_COTAHIST": 1,
        "B3_SPRE": 2,
    }

    prices["SOURCE_PRIORITY"] = (
        prices["SOURCE"]
        .map(source_priority)
        .fillna(0)
    )

    prices = (
        prices
        .sort_values(
            [
                "TICKER",
                "DATE",
                "SOURCE_PRIORITY",
            ]
        )
        .drop_duplicates(
            subset=["TICKER", "DATE"],
            keep="last",
        )
        .drop(columns=["SOURCE_PRIORITY"])
        .sort_values(["TICKER", "DATE"])
        .reset_index(drop=True)
    )

    if prices.empty:
        raise RuntimeError(
            "Nenhum preço B3 disponível."
        )

    print("\n" + "=" * 80)
    print("HISTÓRICO B3 CONSOLIDADO")
    print("=" * 80)
    print("Registros:", len(prices))
    print("Tickers:", prices["TICKER"].nunique())
    print("Primeira data:", prices["DATE"].min())
    print("Última data:", prices["DATE"].max())

    return prices


# ============================================================
# 14. CARREGAR UNIVERSO FUNDAMENTAL LIVE
# ============================================================

def load_fundamental_universe():

    if not FUNDAMENTAL_INPUT_FILE.exists():
        raise FileNotFoundError(
            "\nFundamental LIVE não encontrado:\n"
            f"{FUNDAMENTAL_INPUT_FILE}\n\n"
            "Execute primeiro build_live_fundamental_input.py."
        )

    fundamental = pd.read_csv(
        FUNDAMENTAL_INPUT_FILE,
        low_memory=False,
    )

    fundamental = normalize_columns(fundamental)

    if "TICKER" not in fundamental.columns:
        raise ValueError(
            "fundamental_input_live.csv "
            "não possui TICKER."
        )

    fundamental["TICKER"] = (
        fundamental["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tickers = (
        fundamental["TICKER"]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    print("\n" + "=" * 80)
    print("UNIVERSO FUNDAMENTAL LIVE")
    print("=" * 80)
    print("Tickers:", len(tickers))

    return tickers


# ============================================================
# 15. CARREGAR IDENTIDADE CVM ↔ TICKER
# ============================================================

def load_cvm_ticker_map():

    if not FCA_SECURITY_HISTORY_FILE.exists():
        raise FileNotFoundError(
            "\nHistórico FCA não encontrado:\n"
            f"{FCA_SECURITY_HISTORY_FILE}\n\n"
            "Execute primeiro live_fca_engine.py."
        )

    fca = pd.read_csv(
        FCA_SECURITY_HISTORY_FILE,
        low_memory=False,
    )

    fca = normalize_columns(fca)

    cd_col = find_column(
        fca,
        ["CD_CVM", "CODIGO_CVM"],
    )

    ticker_col = find_column(
        fca,
        [
            "TICKER",
            "CODIGO_NEGOCIACAO",
            "CODIGO_NEGOCIACAO_VALOR_MOBILIARIO",
            "COD_NEGOCIACAO",
        ],
    )

    mapping = fca[
        [cd_col, ticker_col]
    ].copy()

    mapping.columns = [
        "CD_CVM",
        "TICKER",
    ]

    mapping["CD_CVM"] = pd.to_numeric(
        mapping["CD_CVM"],
        errors="coerce",
    )

    mapping["TICKER"] = (
        mapping["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    mapping = (
        mapping
        .dropna(subset=["CD_CVM", "TICKER"])
        .drop_duplicates()
    )

    ambiguous = (
        mapping
        .groupby("TICKER")["CD_CVM"]
        .nunique()
    )

    ambiguous = set(
        ambiguous[
            ambiguous > 1
        ].index
    )

    if ambiguous:
        mapping = mapping[
            ~mapping["TICKER"].isin(ambiguous)
        ].copy()

    mapping = (
        mapping
        .drop_duplicates(
            subset=["TICKER"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return mapping


# ============================================================
# 16. PREPARAR UNIVERSO TÉCNICO
# ============================================================

def prepare_technical_universe(
    prices,
    fundamental_tickers,
    mapping,
):

    prices = prices[
        prices["TICKER"].isin(
            fundamental_tickers
        )
    ].copy()

    prices = prices.merge(
        mapping,
        on="TICKER",
        how="left",
        validate="many_to_one",
    )

    prices = prices.dropna(
        subset=["CD_CVM"]
    )

    prices["CD_CVM"] = pd.to_numeric(
        prices["CD_CVM"],
        errors="coerce",
    )

    prices["SEGMENT_ID"] = 0

    prices = (
        prices
        .sort_values(
            [
                "CD_CVM",
                "SEGMENT_ID",
                "TICKER",
                "DATE",
            ]
        )
        .drop_duplicates(
            subset=[
                "CD_CVM",
                "TICKER",
                "DATE",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    if prices.empty:
        raise RuntimeError(
            "Nenhuma empresa fundamental possui "
            "histórico técnico B3 utilizável."
        )

    return prices


# ============================================================
# 17. DETECTAR RAZÃO MECÂNICA — CELL05B
# ============================================================

def detect_action_ratio(r):

    if pd.isna(r) or r <= 0:
        return np.nan, np.nan

    if abs(r - 1.0) < MIN_ABS_MOVE:
        return np.nan, np.nan

    errors = (
        np.abs(r - ACTION_RATIOS)
        / ACTION_RATIOS
    )

    idx = int(np.argmin(errors))

    candidate = ACTION_RATIOS[idx]
    error = errors[idx]

    if error <= MAX_RELATIVE_ERROR:
        return candidate, error

    return np.nan, np.nan


# ============================================================
# 18. NEUTRALIZAR EVENTOS CORPORATIVOS — CELL05B
# ============================================================

def neutralize_corporate_actions(df):

    df = df.copy()

    print("\n" + "=" * 80)
    print("CELL05B — EVENTOS CORPORATIVOS")
    print("=" * 80)

    group_cols = [
        "CD_CVM",
        "SEGMENT_ID",
        "TICKER",
    ]

    for column in PRICE_COLUMNS:
        df[f"RAW_{column}"] = df[column]

    df["PREV_CLOSE_RAW"] = (
        df.groupby(
            group_cols,
            observed=True,
        )["RAW_CLOSE"]
        .shift(1)
    )

    df["RAW_PRICE_RATIO"] = (
        df["RAW_CLOSE"]
        / df["PREV_CLOSE_RAW"]
    )

    df["RAW_RETURN_1D"] = (
        df["RAW_PRICE_RATIO"] - 1
    )

    detected = (
        df["RAW_PRICE_RATIO"]
        .apply(detect_action_ratio)
    )

    df["DETECTED_ACTION_RATIO"] = [
        item[0] for item in detected
    ]

    df["ACTION_RELATIVE_ERROR"] = [
        item[1] for item in detected
    ]

    df["CORPORATE_ACTION_FLAG"] = (
        df["DETECTED_ACTION_RATIO"].notna()
    )

    df["ACTION_MULTIPLIER"] = np.where(
        df["CORPORATE_ACTION_FLAG"],
        1.0 / df["DETECTED_ACTION_RATIO"],
        1.0,
    )

    df["PRICE_SCALE"] = (
        df.groupby(
            group_cols,
            observed=True,
        )["ACTION_MULTIPLIER"]
        .cumprod()
    )

    for column in PRICE_COLUMNS:
        df[column] = (
            df[f"RAW_{column}"]
            * df["PRICE_SCALE"]
        )

    df["ADJ_RETURN_1D"] = (
        df.groupby(
            group_cols,
            observed=True,
        )["CLOSE"]
        .pct_change(fill_method=None)
    )

    events = df[
        df["CORPORATE_ACTION_FLAG"]
    ].copy()

    event_columns = [
        "DATE",
        "CD_CVM",
        "TICKER",
        "SEGMENT_ID",
        "PREV_CLOSE_RAW",
        "RAW_CLOSE",
        "RAW_PRICE_RATIO",
        "RAW_RETURN_1D",
        "DETECTED_ACTION_RATIO",
        "ACTION_RELATIVE_ERROR",
        "ACTION_MULTIPLIER",
        "PRICE_SCALE",
        "CLOSE",
        "ADJ_RETURN_1D",
    ]

    events[event_columns].to_csv(
        CORPORATE_ACTION_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "Eventos mecânicos detectados:",
        len(events),
    )

    print(
        "Empresas afetadas:",
        events["CD_CVM"].nunique()
        if not events.empty else 0,
    )

    return df


# ============================================================
# 19. ISOLAR DESCONTINUIDADES — CELL06B
# ============================================================

def create_technical_segments(df):

    df = df.copy()

    print("\n" + "=" * 80)
    print("CELL06B — SEGMENTAÇÃO TÉCNICA")
    print("=" * 80)

    group_cols = [
        "CD_CVM",
        "SEGMENT_ID",
        "TICKER",
    ]

    df["RETURN_1D_ADJUSTED"] = (
        df.groupby(
            group_cols,
            observed=True,
        )["CLOSE"]
        .pct_change(fill_method=None)
    )

    df["RESIDUAL_DISCONTINUITY"] = (
        df["RETURN_1D_ADJUSTED"].abs()
        > RESIDUAL_RETURN_LIMIT
    )

    df["RESIDUAL_BREAK_N"] = (
        df.groupby(
            group_cols,
            observed=True,
        )["RESIDUAL_DISCONTINUITY"]
        .cumsum()
    )

    df["TECH_SEGMENT_ID"] = (
        df["SEGMENT_ID"].astype(str)
        + "_"
        + df["RESIDUAL_BREAK_N"].astype(str)
    )

    residuals = df[
        df["RESIDUAL_DISCONTINUITY"]
    ].copy()

    residual_columns = [
        "DATE",
        "CD_CVM",
        "TICKER",
        "SEGMENT_ID",
        "TECH_SEGMENT_ID",
        "RAW_CLOSE",
        "CLOSE",
        "RETURN_1D_ADJUSTED",
        "RESIDUAL_DISCONTINUITY",
    ]

    residuals[residual_columns].to_csv(
        RESIDUAL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "Descontinuidades residuais:",
        len(residuals),
    )

    print(
        "Segmentos técnicos:",
        df[
            [
                "CD_CVM",
                "TICKER",
                "TECH_SEGMENT_ID",
            ]
        ]
        .drop_duplicates()
        .shape[0],
    )

    return df


# ============================================================
# 20. CALCULAR INDICADORES — CELL06B
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    print("\n" + "=" * 80)
    print("CELL06B — 7 INDICADORES CONGELADOS")
    print("=" * 80)

    technical_group = [
        "CD_CVM",
        "SEGMENT_ID",
        "TICKER",
        "TECH_SEGMENT_ID",
    ]

    df = (
        df
        .sort_values(
            technical_group + ["DATE"]
        )
        .reset_index(drop=True)
    )

    df["RETURN_1D"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .pct_change(fill_method=None)
    )

    df["SMA_50"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .transform(
            lambda s:
            s.rolling(
                50,
                min_periods=50,
            ).mean()
        )
    )

    df["DIST_SMA_50"] = (
        df["CLOSE"]
        / df["SMA_50"].replace(0, np.nan)
        - 1
    )

    df["SMA_200"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .transform(
            lambda s:
            s.rolling(
                200,
                min_periods=200,
            ).mean()
        )
    )

    df["DIST_SMA_200"] = (
        df["CLOSE"]
        / df["SMA_200"].replace(0, np.nan)
        - 1
    )

    df["SMA200_SLOPE_20D"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["SMA_200"]
        .transform(
            lambda s:
            (
                s
                / s.shift(20)
                - 1
            )
        )
    )

    df["ROC_60"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .transform(
            lambda s:
            (
                s
                / s.shift(60)
                - 1
            )
        )
    )

    df["EMA_12"] = np.nan
    df["EMA_26"] = np.nan
    df["MACD_RAW"] = np.nan
    df["MACD_SIGNAL_RAW"] = np.nan
    df["MACD_HIST_RAW"] = np.nan

    grouped = df.groupby(
        technical_group,
        observed=True,
        sort=False,
    )

    for _, indexes in grouped.groups.items():

        indexes = list(indexes)

        close = (
            df.loc[indexes, "CLOSE"]
            .astype(float)
        )

        ema12 = (
            close.ewm(
                span=12,
                adjust=False,
                min_periods=12,
            ).mean()
        )

        ema26 = (
            close.ewm(
                span=26,
                adjust=False,
                min_periods=26,
            ).mean()
        )

        macd = ema12 - ema26

        signal = (
            macd.ewm(
                span=9,
                adjust=False,
                min_periods=9,
            ).mean()
        )

        histogram = macd - signal

        df.loc[
            indexes,
            "EMA_12",
        ] = ema12.to_numpy()

        df.loc[
            indexes,
            "EMA_26",
        ] = ema26.to_numpy()

        df.loc[
            indexes,
            "MACD_RAW",
        ] = macd.to_numpy()

        df.loc[
            indexes,
            "MACD_SIGNAL_RAW",
        ] = signal.to_numpy()

        df.loc[
            indexes,
            "MACD_HIST_RAW",
        ] = histogram.to_numpy()

    df["MACD_HIST_PCT"] = (
        df["MACD_HIST_RAW"]
        / df["CLOSE"].replace(0, np.nan)
    )

    # Bollinger 20,2 — Cell06B: std(ddof=0)

    df["BB_MID"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .transform(
            lambda s:
            s.rolling(
                20,
                min_periods=20,
            ).mean()
        )
    )

    df["BB_STD"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .transform(
            lambda s:
            s.rolling(
                20,
                min_periods=20,
            ).std(ddof=0)
        )
    )

    df["BB_UPPER"] = (
        df["BB_MID"]
        + 2 * df["BB_STD"]
    )

    df["BB_LOWER"] = (
        df["BB_MID"]
        - 2 * df["BB_STD"]
    )

    bb_range = (
        df["BB_UPPER"]
        - df["BB_LOWER"]
    )

    df["BB_WIDTH"] = (
        bb_range
        / df["BB_MID"].replace(0, np.nan)
    )

    df["PREV_CLOSE"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["CLOSE"]
        .shift(1)
    )

    tr1 = df["HIGH"] - df["LOW"]

    tr2 = (
        df["HIGH"]
        - df["PREV_CLOSE"]
    ).abs()

    tr3 = (
        df["LOW"]
        - df["PREV_CLOSE"]
    ).abs()

    df["TRUE_RANGE"] = (
        pd.concat(
            [tr1, tr2, tr3],
            axis=1,
        )
        .max(axis=1)
    )

    df["ATR_14"] = (
        df.groupby(
            technical_group,
            observed=True,
        )["TRUE_RANGE"]
        .transform(
            lambda s:
            s.rolling(
                14,
                min_periods=14,
            ).mean()
        )
    )

    df["ATR_PCT"] = (
        df["ATR_14"]
        / df["CLOSE"].replace(0, np.nan)
    )

    return df


# ============================================================
# 21. EXTRAIR SAÍDA DE PRODUÇÃO
# ============================================================

def extract_production_data(df):

    missing = [
        column
        for column in OUTPUT_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Colunas técnicas ausentes após cálculo: "
            f"{missing}"
        )

    output = df[
        OUTPUT_COLUMNS
    ].copy()

    output = (
        output
        .sort_values(
            [
                "CD_CVM",
                "TICKER",
                "DATE",
            ]
        )
        .drop_duplicates(
            subset=[
                "CD_CVM",
                "TICKER",
                "DATE",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return output


# ============================================================
# 22. AUDITORIA
# ============================================================

def audit_technical_data(
    technical,
    fundamental_tickers,
):

    print("\n" + "=" * 80)
    print("AUDITORIA TÉCNICA LIVE")
    print("=" * 80)

    if technical.empty:
        raise RuntimeError(
            "Base técnica LIVE vazia."
        )

    duplicates = technical.duplicated(
        subset=[
            "CD_CVM",
            "TICKER",
            "DATE",
        ]
    ).sum()

    if duplicates:
        raise RuntimeError(
            "Duplicidades CD_CVM/TICKER/DATE "
            "na base técnica LIVE."
        )

    invalid_ohlc = technical[
        (
            technical["HIGH"]
            <
            technical[
                ["OPEN", "LOW", "CLOSE"]
            ].max(axis=1)
        )
        |
        (
            technical["LOW"]
            >
            technical[
                ["OPEN", "HIGH", "CLOSE"]
            ].min(axis=1)
        )
    ]

    if not invalid_ohlc.empty:
        raise RuntimeError(
            "OHLC inválido após ajuste técnico."
        )

    technical_tickers = set(
        technical["TICKER"]
        .dropna()
        .unique()
    )

    fundamental_set = set(
        fundamental_tickers
    )

    missing_tickers = sorted(
        fundamental_set
        - technical_tickers
    )

    print(
        "Empresas fundamentais:",
        len(fundamental_set),
    )

    print(
        "Empresas com histórico técnico:",
        len(technical_tickers),
    )

    print(
        "Empresas sem histórico técnico:",
        len(missing_tickers),
    )

    print("Registros:", len(technical))

    print(
        "Segmentos técnicos:",
        technical[
            "TECH_SEGMENT_ID"
        ].nunique(),
    )

    print(
        "Primeira data:",
        technical["DATE"].min(),
    )

    print(
        "Última data:",
        technical["DATE"].max(),
    )

    print("\n7 INDICADORES:")

    for indicator in TECHNICAL_INDICATORS:

        valid = int(
            technical[indicator]
            .notna()
            .sum()
        )

        missing = int(
            technical[indicator]
            .isna()
            .sum()
        )

        print(
            f"{indicator:<22} "
            f"válidos={valid:<10} "
            f"NaN={missing}"
        )

    forbidden_columns = [
        "TECHNICAL_SCORE",
        "BUY_SIGNAL",
        "SELL_SIGNAL",
        "MANDATORY_TRIGGER",
        "VALIDATED_OOS_TRIGGER",
    ]

    violations = [
        column
        for column in forbidden_columns
        if column in technical.columns
    ]

    if violations:
        raise RuntimeError(
            "Violação da arquitetura técnica. "
            f"Colunas proibidas: {violations}"
        )

    if missing_tickers:

        print("\nATENÇÃO:")

        print(
            "Ausência de contexto técnico NÃO reprova "
            "empresa fundamentalmente aprovada."
        )

    return {
        "missing_tickers":
            missing_tickers,
    }


# ============================================================
# 23. AUDITORIA DE ATUALIDADE
# ============================================================

def audit_freshness(technical):

    latest_date = technical["DATE"].max()

    if pd.isna(latest_date):
        raise RuntimeError(
            "Não foi possível determinar "
            "a data mais recente da base técnica."
        )

    now_utc = pd.Timestamp.now(
        tz="UTC"
    ).tz_localize(None)

    age_days = (
        now_utc.normalize()
        - pd.Timestamp(latest_date).normalize()
    ).days

    print("\n" + "=" * 80)
    print("ATUALIDADE DA BASE TÉCNICA")
    print("=" * 80)

    print(
        "Último pregão disponível:",
        pd.Timestamp(latest_date).date(),
    )

    print(
        "Defasagem calendário:",
        age_days,
        "dias",
    )

    if age_days > 10:
        raise RuntimeError(
            "\nBASE TÉCNICA DESATUALIZADA.\n\n"
            f"Última data disponível: {latest_date}\n"
            f"Defasagem: {age_days} dias.\n\n"
            "O robô não continuará utilizando "
            "indicadores técnicos antigos como se fossem atuais."
        )

    return latest_date


# ============================================================
# 24. MANIFESTO
# ============================================================

def save_manifest(
    technical,
    audit,
    latest_date,
):

    latest_rows = (
        technical
        .sort_values("DATE")
        .groupby(
            "TICKER",
            as_index=False,
        )
        .tail(1)
    )

    latest_complete = (
        latest_rows[
            TECHNICAL_INDICATORS
        ]
        .notna()
        .all(axis=1)
        .sum()
    )

    manifest = {

        "engine":
            "B3_INVESTMENT_ENGINE",

        "stage":
            "TECHNICAL_LIVE",

        "version":
            "LIVE_CELL05B_CELL06B",

        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "market_history_source":
            str(MARKET_HISTORY_FILE),

        "current_year_source":
            str(SPRE_PRICES_FILE),

        "fundamental_source":
            str(FUNDAMENTAL_INPUT_FILE),

        "rows":
            int(len(technical)),

        "companies":
            int(
                technical["CD_CVM"]
                .nunique()
            ),

        "tickers":
            int(
                technical["TICKER"]
                .nunique()
            ),

        "technical_segments":
            int(
                technical[
                    "TECH_SEGMENT_ID"
                ].nunique()
            ),

        "latest_market_date":
            str(
                pd.Timestamp(
                    latest_date
                ).date()
            ),

        "latest_complete_technical_context":
            int(latest_complete),

        "missing_fundamental_tickers":
            audit["missing_tickers"],

        "corporate_action_method":
            "MECHANICAL_DISCONTINUITY_NEUTRALIZATION",

        "min_abs_move":
            MIN_ABS_MOVE,

        "max_relative_error":
            MAX_RELATIVE_ERROR,

        "residual_return_limit":
            RESIDUAL_RETURN_LIMIT,

        "technical_indicators":
            TECHNICAL_INDICATORS,

        "technical_score_created":
            False,

        "mandatory_trigger_created":
            False,

        "oos_research_reexecuted":
            False,

        "fundamental_engine_modified":
            False,

        "ranking_modified":
            False,

        "data_mode":
            "LIVE",

        "methodology_mode":
            "FROZEN",
    }

    with open(
        MANIFEST_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# 25. EXECUÇÃO
# ============================================================

def main():

    print("=" * 80)
    print("B3 INVESTMENT ENGINE")
    print("BUILD TECHNICAL PRICES — LIVE")
    print("=" * 80)

    fundamental_tickers = (
        load_fundamental_universe()
    )

    mapping = (
        load_cvm_ticker_map()
    )

    prices = (
        build_price_history()
    )

    technical = (
        prepare_technical_universe(
            prices,
            fundamental_tickers,
            mapping,
        )
    )

    print("\n" + "=" * 80)
    print("UNIVERSO TÉCNICO LIVE")
    print("=" * 80)

    print("Registros:", len(technical))

    print(
        "Empresas:",
        technical["CD_CVM"].nunique(),
    )

    print(
        "Tickers:",
        technical["TICKER"].nunique(),
    )

    technical = (
        neutralize_corporate_actions(
            technical
        )
    )

    technical = (
        create_technical_segments(
            technical
        )
    )

    technical = (
        calculate_indicators(
            technical
        )
    )

    production = (
        extract_production_data(
            technical
        )
    )

    audit = (
        audit_technical_data(
            production,
            fundamental_tickers,
        )
    )

    latest_date = (
        audit_freshness(
            production
        )
    )

    production.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    save_manifest(
        production,
        audit,
        latest_date,
    )

    print("\n" + "=" * 80)
    print("✓ technical_prices_live.csv criado.")
    print("✓ Dados técnicos: LIVE.")
    print("✓ Metodologia: CONGELADA.")
    print("✓ Eventos corporativos Cell05B recalculados.")
    print("✓ Segmentação Cell06B recalculada.")
    print("✓ SMA200_SLOPE_20D recalculado.")
    print("✓ ATR_PCT recalculado.")
    print("✓ ROC_60 recalculado.")
    print("✓ MACD_HIST_PCT recalculado.")
    print("✓ DIST_SMA_200 recalculado.")
    print("✓ BB_WIDTH recalculado.")
    print("✓ DIST_SMA_50 recalculado.")
    print("✓ Nenhum Technical Score criado.")
    print("✓ Nenhum gatilho técnico obrigatório criado.")
    print("✓ Ranking fundamental não foi alterado.")
    print("✓ Técnico permanece somente como contexto.")

    print(
        "\nÚltimo pregão:",
        pd.Timestamp(latest_date).date(),
    )

    print("\nArquivo:")
    print(OUTPUT_FILE)

    print("\nManifesto:")
    print(MANIFEST_FILE)

    print("=" * 80)


# ============================================================
# 26. START
# ============================================================

if __name__ == "__main__":
    main()
