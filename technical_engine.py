# ============================================================
# B3_INVESTMENT_ENGINE
# technical_engine.py
#
# Technical Timing Engine
#
# PAPEL:
# - Executado somente após a análise fundamental.
# - Consome os 7 indicadores congelados do estudo Cell06B.
# - NÃO recalcula indicadores técnicos.
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
# 1. INDICADORES CONGELADOS
# ============================================================

FROZEN_INDICATORS = [
    "SMA200_SLOPE_20D",
    "ATR_PCT",
    "ROC_60",
    "MACD_HIST_PCT",
    "DIST_SMA_200",
    "BB_WIDTH",
    "DIST_SMA_50",
]


# ============================================================
# 2. RESULTADO DO MOTOR TÉCNICO
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
# 3. CONVERTER NÚMERO
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
# 4. VALIDAR DADOS TÉCNICOS
# ============================================================

def prepare_technical_data(
    df: pd.DataFrame
) -> pd.DataFrame:

    required = [
        "TICKER",
        "DATE",
        "TECH_SEGMENT_ID",
        *FROZEN_INDICATORS,
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Colunas técnicas congeladas ausentes: "
            f"{missing}"
        )

    data = df.copy()

    data["TICKER"] = (
        data["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    data["DATE"] = pd.to_datetime(
        data["DATE"],
        errors="coerce",
    )

    for indicator in FROZEN_INDICATORS:

        data[indicator] = pd.to_numeric(
            data[indicator],
            errors="coerce",
        )

    data = (
        data
        .dropna(
            subset=[
                "TICKER",
                "DATE",
                "TECH_SEGMENT_ID",
            ]
        )
        .sort_values(
            [
                "DATE",
            ]
        )
        .drop_duplicates(
            subset=[
                "TICKER",
                "DATE",
            ],
            keep="last",
        )
        .reset_index(
            drop=True
        )
    )

    return data


# ============================================================
# 5. OBSERVAÇÕES TÉCNICAS
# ============================================================
#
# São somente descrições matemáticas.
#
# NÃO representam:
# - BUY
# - SELL
# - score
# - veto
# - gatilho validado
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

        else:

            observations.append(
                "PRECO_NA_SMA50"
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

        else:

            observations.append(
                "PRECO_NA_SMA200"
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

        else:

            observations.append(
                "MACD_HIST_NEUTRO"
            )

    if not observations:

        return "SEM_CONTEXTO_TECNICO"

    return "|".join(
        observations
    )


# ============================================================
# 6. RESULTADO SEM APLICAÇÃO TÉCNICA
# ============================================================

def _not_applicable_result(
    ticker: str
) -> TechnicalResult:

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


# ============================================================
# 7. RESULTADO SEM DADOS TÉCNICOS
# ============================================================

def _unavailable_result(
    ticker: str,
    reason: str,
) -> TechnicalResult:

    return TechnicalResult(

        ticker=ticker,

        technical_available=False,

        technical_role=(
            "ENTRY_CONTEXT"
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

        observations=reason,
    )


# ============================================================
# 8. AVALIAR UM TICKER
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
    # Empresa fundamentalmente reprovada não pode ser
    # recuperada pelo técnico.
    # --------------------------------------------------------

    if not fundamental_approved:

        return _not_applicable_result(
            ticker
        )

    # --------------------------------------------------------
    # Sem base técnica
    # --------------------------------------------------------

    if prices is None or prices.empty:

        return _unavailable_result(
            ticker=ticker,
            reason="SEM_DADOS_TECNICOS",
        )

    # --------------------------------------------------------
    # Ler indicadores congelados
    # --------------------------------------------------------

    data = prepare_technical_data(
        prices
    )

    data = data[
        data["TICKER"] == ticker
    ].copy()

    if data.empty:

        return _unavailable_result(
            ticker=ticker,
            reason="SEM_DADOS_TECNICOS",
        )

    # --------------------------------------------------------
    # Último registro disponível do checkpoint congelado
    # --------------------------------------------------------

    latest = (
        data
        .sort_values("DATE")
        .iloc[-1]
    )

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
        len(FROZEN_INDICATORS)
    )

    observations = build_observations(
        latest
    )

    if not technical_available:

        observations = (
            "CONTEXTO_TECNICO_INCOMPLETO"
            + (
                "|"
                + observations

                if observations
                != "SEM_CONTEXTO_TECNICO"

                else ""
            )
        )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

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
# 9. RESULTADO → DICIONÁRIO
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
# 10. AUTOTESTE
# ============================================================
#
# O autoteste não calcula indicadores.
# Ele fornece diretamente os indicadores congelados,
# exatamente como ocorrerá em produção.
# ============================================================

def self_test():

    dates = pd.bdate_range(
        start="2025-12-22",
        periods=5,
    )

    test_data = pd.DataFrame({

        "CD_CVM": [
            99999,
            99999,
            99999,
            99999,
            99999,
        ],

        "TICKER": [
            "TEST3",
            "TEST3",
            "TEST3",
            "TEST3",
            "TEST3",
        ],

        "DATE":
            dates,

        "TECH_SEGMENT_ID": [
            "0_0",
            "0_0",
            "0_0",
            "0_0",
            "0_0",
        ],

        "OPEN": [
            10.0,
            10.1,
            10.2,
            10.3,
            10.4,
        ],

        "HIGH": [
            10.2,
            10.3,
            10.4,
            10.5,
            10.6,
        ],

        "LOW": [
            9.8,
            9.9,
            10.0,
            10.1,
            10.2,
        ],

        "CLOSE": [
            10.1,
            10.2,
            10.3,
            10.4,
            10.5,
        ],

        "SMA200_SLOPE_20D": [
            0.01,
            0.011,
            0.012,
            0.013,
            0.014,
        ],

        "ATR_PCT": [
            0.03,
            0.031,
            0.032,
            0.033,
            0.034,
        ],

        "ROC_60": [
            0.05,
            0.06,
            0.07,
            0.08,
            0.09,
        ],

        "MACD_HIST_PCT": [
            -0.01,
            -0.005,
            0.001,
            0.003,
            0.005,
        ],

        "DIST_SMA_200": [
            0.02,
            0.025,
            0.03,
            0.035,
            0.04,
        ],

        "BB_WIDTH": [
            0.10,
            0.11,
            0.12,
            0.13,
            0.14,
        ],

        "DIST_SMA_50": [
            0.01,
            0.015,
            0.02,
            0.025,
            0.03,
        ],
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

    assert (
        approved.sma200_slope_20d
        ==
        0.014
    )

    assert (
        approved.roc_60
        ==
        0.09
    )

    assert (
        approved.macd_hist_pct
        ==
        0.005
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

    assert (
        set(
            TECHNICAL_CONTEXT_INDICATORS
        )
        ==
        set(
            FROZEN_INDICATORS
        )
    )

    print(
        "✓ Technical Timing Engine: "
        "autoteste aprovado."
    )


# ============================================================
# 11. EXECUÇÃO DIRETA
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
        "✓ 7 indicadores técnicos congelados preservados."
    )

    print(
        "✓ Indicadores NÃO são recalculados."
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
