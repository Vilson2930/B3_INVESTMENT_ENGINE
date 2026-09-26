# ============================================================
# B3_INVESTMENT_ENGINE
# technical_engine.py
#
# Technical Timing Engine
#
# PAPEL:
# - Executado somente após a análise fundamental.
# - Calcula os 7 indicadores preservados pelo estudo.
# - NÃO cria Technical Score.
# - NÃO veta empresa fundamentalmente aprovada.
# - NÃO recupera empresa reprovada nos fundamentos.
# ============================================================

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    PROJECT_NAME,
    TECHNICAL_ENGINE_VERSION,
    TECHNICAL_ENGINE_MODE,
    TECHNICAL_CONTEXT_INDICATORS,
    TECHNICAL_MANDATORY_TRIGGER,
    TECHNICAL_CAN_VETO_FUNDAMENTAL,
    TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL,
    TECHNICAL_SCORE_ENABLED,
    OOS_VALIDATED_MANDATORY_PAIRS,
    validate_config,
)


# ============================================================
# 1. RESULTADO DO MOTOR TÉCNICO
# ============================================================

@dataclass
class TechnicalResult:

    ticker: str

    technical_available: bool

    technical_role: str

    technical_engine_version: str

    technical_engine_mode: str

    technical_score: Optional[float]

    mandatory_trigger: bool

    validated_oos_trigger: bool

    sma200_slope_20d: Optional[float]

    atr_pct: Optional[float]

    roc_60: Optional[float]

    macd_hist_pct: Optional[float]

    dist_sma_200: Optional[float]

    bb_width: Optional[float]

    dist_sma_50: Optional[float]

    observations: str


# ============================================================
# 2. VALIDAÇÃO DA SÉRIE
# ============================================================

def prepare_prices(df: pd.DataFrame) -> pd.DataFrame:

    required = [
        "DATE",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Colunas ausentes: {missing}"
        )

    data = df.copy()

    data["DATE"] = pd.to_datetime(
        data["DATE"],
        errors="coerce"
    )

    for col in [
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]:

        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        )

    data = (
        data
        .dropna(
            subset=[
                "DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
            ]
        )
        .sort_values("DATE")
        .drop_duplicates(
            subset=["DATE"],
            keep="last"
        )
        .reset_index(drop=True)
    )

    invalid = (
        (data["OPEN"] <= 0)
        | (data["HIGH"] <= 0)
        | (data["LOW"] <= 0)
        | (data["CLOSE"] <= 0)
        | (data["HIGH"] < data["LOW"])
    )

    if invalid.any():

        raise ValueError(
            "Série OHLC contém valores inválidos."
        )

    return data


# ============================================================
# 3. MÉDIAS MÓVEIS
# ============================================================

def add_moving_averages(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    data["SMA_50"] = (
        data["CLOSE"]
        .rolling(
            window=50,
            min_periods=50
        )
        .mean()
    )

    data["SMA_200"] = (
        data["CLOSE"]
        .rolling(
            window=200,
            min_periods=200
        )
        .mean()
    )

    return data


# ============================================================
# 4. SMA200 SLOPE 20D
# ============================================================

def add_sma200_slope(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    data["SMA200_SLOPE_20D"] = (
        data["SMA_200"]
        /
        data["SMA_200"].shift(20)
        - 1.0
    )

    return data


# ============================================================
# 5. DISTÂNCIA DAS MÉDIAS
# ============================================================

def add_distance_from_ma(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    data["DIST_SMA_50"] = (
        data["CLOSE"]
        /
        data["SMA_50"]
        - 1.0
    )

    data["DIST_SMA_200"] = (
        data["CLOSE"]
        /
        data["SMA_200"]
        - 1.0
    )

    return data


# ============================================================
# 6. ROC 60
# ============================================================

def add_roc_60(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    data["ROC_60"] = (
        data["CLOSE"]
        /
        data["CLOSE"].shift(60)
        - 1.0
    )

    return data


# ============================================================
# 7. ATR PERCENTUAL
# ============================================================

def add_atr_pct(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    previous_close = (
        data["CLOSE"].shift(1)
    )

    tr1 = (
        data["HIGH"]
        - data["LOW"]
    )

    tr2 = (
        data["HIGH"]
        - previous_close
    ).abs()

    tr3 = (
        data["LOW"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1
    ).max(axis=1)

    atr14 = (
        true_range
        .rolling(
            window=14,
            min_periods=14
        )
        .mean()
    )

    data["ATR_PCT"] = (
        atr14
        /
        data["CLOSE"]
    )

    return data


# ============================================================
# 8. MACD HISTOGRAM PERCENTUAL
# ============================================================

def add_macd_hist_pct(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    ema12 = (
        data["CLOSE"]
        .ewm(
            span=12,
            adjust=False,
            min_periods=12
        )
        .mean()
    )

    ema26 = (
        data["CLOSE"]
        .ewm(
            span=26,
            adjust=False,
            min_periods=26
        )
        .mean()
    )

    macd = (
        ema12
        - ema26
    )

    signal = (
        macd
        .ewm(
            span=9,
            adjust=False,
            min_periods=9
        )
        .mean()
    )

    histogram = (
        macd
        - signal
    )

    data["MACD_HIST_PCT"] = (
        histogram
        /
        data["CLOSE"]
    )

    return data


# ============================================================
# 9. BOLLINGER WIDTH
# ============================================================

def add_bb_width(
    data: pd.DataFrame
) -> pd.DataFrame:

    data = data.copy()

    sma20 = (
        data["CLOSE"]
        .rolling(
            window=20,
            min_periods=20
        )
        .mean()
    )

    std20 = (
        data["CLOSE"]
        .rolling(
            window=20,
            min_periods=20
        )
        .std(ddof=0)
    )

    upper = (
        sma20
        + 2.0 * std20
    )

    lower = (
        sma20
        - 2.0 * std20
    )

    data["BB_WIDTH"] = (
        (upper - lower)
        /
        sma20
    )

    return data


# ============================================================
# 10. CALCULAR TODOS OS INDICADORES
# ============================================================

def calculate_indicators(
    df: pd.DataFrame
) -> pd.DataFrame:

    data = prepare_prices(df)

    data = add_moving_averages(
        data
    )

    data = add_sma200_slope(
        data
    )

    data = add_distance_from_ma(
        data
    )

    data = add_roc_60(
        data
    )

    data = add_atr_pct(
        data
    )

    data = add_macd_hist_pct(
        data
    )

    data = add_bb_width(
        data
    )

    return data


# ============================================================
# 11. CONVERTER NÚMERO
# ============================================================

def _safe_float(value):

    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(value):
        return None

    return value


# ============================================================
# 12. OBSERVAÇÕES TÉCNICAS
# ============================================================
#
# IMPORTANTE:
#
# São descrições matemáticas do estado atual.
# Não são BUY / SELL.
# Não são gatilhos validados.
# ============================================================

def build_observations(
    latest: pd.Series
) -> str:

    observations = []

    slope = _safe_float(
        latest.get(
            "SMA200_SLOPE_20D"
        )
    )

    roc60 = _safe_float(
        latest.get(
            "ROC_60"
        )
    )

    dist50 = _safe_float(
        latest.get(
            "DIST_SMA_50"
        )
    )

    dist200 = _safe_float(
        latest.get(
            "DIST_SMA_200"
        )
    )

    macd_hist = _safe_float(
        latest.get(
            "MACD_HIST_PCT"
        )
    )

    if slope is not None:

        if slope > 0:

            observations.append(
                "SMA200_INCLINACAO_POSITIVA"
            )

        elif slope < 0:

            observations.append(
                "SMA200_INCLINACAO_NEGATIVA"
            )

        else:

            observations.append(
                "SMA200_ESTAVEL"
            )

    if roc60 is not None:

        if roc60 > 0:

            observations.append(
                "ROC60_POSITIVO"
            )

        elif roc60 < 0:

            observations.append(
                "ROC60_NEGATIVO"
            )

        else:

            observations.append(
                "ROC60_NEUTRO"
            )

    if dist50 is not None:

        if dist50 > 0:

            observations.append(
                "PRECO_ACIMA_SMA50"
            )

        elif dist50 < 0:

            observations.append(
                "PRECO_ABAIXO_SMA50"
            )

    if dist200 is not None:

        if dist200 > 0:

            observations.append(
                "PRECO_ACIMA_SMA200"
            )

        elif dist200 < 0:

            observations.append(
                "PRECO_ABAIXO_SMA200"
            )

    if macd_hist is not None:

        if macd_hist > 0:

            observations.append(
                "MACD_HIST_POSITIVO"
            )

        elif macd_hist < 0:

            observations.append(
                "MACD_HIST_NEGATIVO"
            )

    if not observations:

        return "SEM_CONTEXTO_TECNICO"

    return "|".join(
        observations
    )


# ============================================================
# 13. AVALIAR UM TICKER
# ============================================================

def evaluate_ticker(
    ticker: str,
    prices: pd.DataFrame,
    fundamental_approved: bool,
) -> TechnicalResult:

    ticker = str(
        ticker
    ).strip().upper()

    if not ticker:

        raise ValueError(
            "Ticker vazio."
        )

    # --------------------------------------------------------
    # REGRA CENTRAL
    # --------------------------------------------------------
    #
    # O motor técnico não deve transformar empresa
    # fundamentalmente reprovada em elegível.
    # --------------------------------------------------------

    if not fundamental_approved:

        return TechnicalResult(

            ticker=ticker,

            technical_available=False,

            technical_role=(
                "NOT_APPLICABLE"
            ),

            technical_engine_version=(
                TECHNICAL_ENGINE_VERSION
            ),

            technical_engine_mode=(
                TECHNICAL_ENGINE_MODE
            ),

            technical_score=None,

            mandatory_trigger=False,

            validated_oos_trigger=False,

            sma200_slope_20d=None,

            atr_pct=None,

            roc_60=None,

            macd_hist_pct=None,

            dist_sma_200=None,

            bb_width=None,

            dist_sma_50=None,

            observations=(
                "FUNDAMENTAL_NOT_APPROVED"
            ),
        )

    data = calculate_indicators(
        prices
    )

    if data.empty:

        raise ValueError(
            f"Sem dados técnicos para {ticker}."
        )

    latest = data.iloc[-1]

    values = {
        "SMA200_SLOPE_20D":
            _safe_float(
                latest.get(
                    "SMA200_SLOPE_20D"
                )
            ),

        "ATR_PCT":
            _safe_float(
                latest.get(
                    "ATR_PCT"
                )
            ),

        "ROC_60":
            _safe_float(
                latest.get(
                    "ROC_60"
                )
            ),

        "MACD_HIST_PCT":
            _safe_float(
                latest.get(
                    "MACD_HIST_PCT"
                )
            ),

        "DIST_SMA_200":
            _safe_float(
                latest.get(
                    "DIST_SMA_200"
                )
            ),

        "BB_WIDTH":
            _safe_float(
                latest.get(
                    "BB_WIDTH"
                )
            ),

        "DIST_SMA_50":
            _safe_float(
                latest.get(
                    "DIST_SMA_50"
                )
            ),
    }

    available_count = sum(
        value is not None
        for value in values.values()
    )

    technical_available = (
        available_count
        ==
        len(
            TECHNICAL_CONTEXT_INDICATORS
        )
    )

    observations = build_observations(
        latest
    )

    return TechnicalResult(

        ticker=ticker,

        technical_available=(
            technical_available
        ),

        technical_role=(
            "ENTRY_CONTEXT"
        ),

        technical_engine_version=(
            TECHNICAL_ENGINE_VERSION
        ),

        technical_engine_mode=(
            TECHNICAL_ENGINE_MODE
        ),

        # Não existe Technical Score validado.
        technical_score=None,

        # Nenhum par obrigatório sobreviveu ao OOS.
        mandatory_trigger=False,

        validated_oos_trigger=False,

        sma200_slope_20d=(
            values[
                "SMA200_SLOPE_20D"
            ]
        ),

        atr_pct=(
            values[
                "ATR_PCT"
            ]
        ),

        roc_60=(
            values[
                "ROC_60"
            ]
        ),

        macd_hist_pct=(
            values[
                "MACD_HIST_PCT"
            ]
        ),

        dist_sma_200=(
            values[
                "DIST_SMA_200"
            ]
        ),

        bb_width=(
            values[
                "BB_WIDTH"
            ]
        ),

        dist_sma_50=(
            values[
                "DIST_SMA_50"
            ]
        ),

        observations=(
            observations
        ),
    )


# ============================================================
# 14. RESULTADO → DICIONÁRIO
# ============================================================

def result_to_dict(
    result: TechnicalResult
) -> dict:

    data = asdict(
        result
    )

    return {
        key.upper(): value
        for key, value in data.items()
    }


# ============================================================
# 15. AUTOTESTE
# ============================================================

def self_test():

    np.random.seed(42)

    dates = pd.bdate_range(
        start="2024-01-01",
        periods=320
    )

    base = np.linspace(
        20.0,
        30.0,
        len(dates)
    )

    noise = np.random.normal(
        0.0,
        0.15,
        len(dates)
    )

    close = (
        base
        + noise
    )

    close = np.maximum(
        close,
        1.0
    )

    test_data = pd.DataFrame({

        "DATE":
            dates,

        "OPEN":
            close * 0.998,

        "HIGH":
            close * 1.015,

        "LOW":
            close * 0.985,

        "CLOSE":
            close,
    })

    # --------------------------------------------------------
    # Empresa fundamentalmente aprovada
    # --------------------------------------------------------

    approved = evaluate_ticker(

        ticker="TEST3",

        prices=test_data,

        fundamental_approved=True,
    )

    assert (
        approved.technical_role
        ==
        "ENTRY_CONTEXT"
    )

    assert (
        approved.technical_score
        is None
    )

    assert (
        approved.mandatory_trigger
        is False
    )

    assert (
        approved.validated_oos_trigger
        is False
    )

    assert (
        approved.technical_available
        is True
    )

    # --------------------------------------------------------
    # Empresa fundamentalmente reprovada
    # --------------------------------------------------------

    rejected = evaluate_ticker(

        ticker="TEST4",

        prices=test_data,

        fundamental_approved=False,
    )

    assert (
        rejected.technical_available
        is False
    )

    assert (
        rejected.technical_role
        ==
        "NOT_APPLICABLE"
    )

    assert (
        rejected.observations
        ==
        "FUNDAMENTAL_NOT_APPROVED"
    )

    # --------------------------------------------------------
    # Regras congeladas
    # --------------------------------------------------------

    assert (
        TECHNICAL_MANDATORY_TRIGGER
        is False
    )

    assert (
        TECHNICAL_CAN_VETO_FUNDAMENTAL
        is False
    )

    assert (
        TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL
        is False
    )

    assert (
        TECHNICAL_SCORE_ENABLED
        is False
    )

    assert (
        OOS_VALIDATED_MANDATORY_PAIRS
        ==
        0
    )

    assert (
        len(
            TECHNICAL_CONTEXT_INDICATORS
        )
        ==
        7
    )

    print(
        "✓ Technical Timing Engine: "
        "autoteste aprovado."
    )


# ============================================================
# 16. EXECUÇÃO DIRETA
# ============================================================

if __name__ == "__main__":

    validate_config()

    print("=" * 72)
    print(PROJECT_NAME)
    print("TECHNICAL TIMING ENGINE")
    print("=" * 72)

    self_test()

    print(
        f"✓ Versão: "
        f"{TECHNICAL_ENGINE_VERSION}"
    )

    print(
        f"✓ Modo: "
        f"{TECHNICAL_ENGINE_MODE}"
    )

    print(
        "✓ 7 indicadores técnicos preservados."
    )

    print(
        "✓ Technical Score: DESATIVADO."
    )

    print(
        "✓ Gatilho técnico obrigatório: DESATIVADO."
    )

    print(
        "✓ Técnico não veta fundamento aprovado."
    )

    print(
        "✓ Técnico não recupera fundamento reprovado."
    )

    print(
        "✓ Motor técnico funciona como "
        "contexto de timing."
    )
