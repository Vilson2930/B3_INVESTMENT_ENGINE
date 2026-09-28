"""
B3 INVESTMENT ENGINE
B3 INVESTABILITY V1

Reprodução modular da Cell19 do estudo original.

ORDEM METODOLÓGICA
------------------
Este módulo recebe SOMENTE empresas já aprovadas pelo
Quality Engine.

Depois aplica:

1. histórico mínimo de negociação >= 10 anos;
2. liquidez média diária >= R$ 6 milhões.

IMPORTANTE
----------
- mudança de ticker NÃO reinicia o histórico da companhia;
- histórico é consolidado por CD_CVM;
- liquidez é calculada por ticker e depois associada à empresa;
- o ticker representativo é o de maior liquidez;
- valuation NÃO participa;
- análise técnica NÃO participa;
- Quality Score NÃO é alterado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ============================================================
# 1. PARÂMETROS CONGELADOS
# ============================================================

MIN_HISTORY_YEARS = 10.0

MIN_AVG_DAILY_LIQUIDITY_BRL = (
    6_000_000.0
)

DAYS_PER_YEAR = 365.2425


# ============================================================
# 2. RESULTADO
# ============================================================

@dataclass(frozen=True)
class InvestabilityConfig:

    reference_date: pd.Timestamp

    liquidity_reference_year: int

    min_history_years: float = (
        MIN_HISTORY_YEARS
    )

    min_avg_daily_liquidity_brl: float = (
        MIN_AVG_DAILY_LIQUIDITY_BRL
    )


# ============================================================
# 3. NORMALIZAÇÃO DE TICKER
# ============================================================

def normalize_ticker(value):

    if pd.isna(value):
        return np.nan

    value = (
        str(value)
        .strip()
        .upper()
    )

    if not value:
        return np.nan

    return value


# ============================================================
# 4. VALIDAÇÃO DO MAPA HISTÓRICO
# ============================================================

def validate_ticker_history(
    ticker_history: pd.DataFrame,
) -> pd.DataFrame:

    required = {
        "CD_CVM",
        "TICKER",
    }

    missing = (
        required
        - set(ticker_history.columns)
    )

    if missing:

        raise ValueError(
            "Histórico de tickers sem colunas "
            "obrigatórias: "
            + ", ".join(sorted(missing))
        )

    history = ticker_history.copy()

    history["TICKER"] = (
        history["TICKER"]
        .map(normalize_ticker)
    )

    history = history[
        history["TICKER"].notna()
    ].copy()

    history = (
        history[
            [
                "CD_CVM",
                "TICKER",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    if history.empty:

        raise ValueError(
            "Histórico de tickers vazio."
        )

    return history


# ============================================================
# 5. VALIDAÇÃO DO COTAHIST
# ============================================================

def validate_market_history(
    market_history: pd.DataFrame,
) -> pd.DataFrame:

    required = {
        "TICKER",
        "DATA",
        "VOLTOT",
    }

    missing = (
        required
        - set(market_history.columns)
    )

    if missing:

        raise ValueError(
            "COTAHIST sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    market = market_history.copy()

    market["TICKER"] = (
        market["TICKER"]
        .map(normalize_ticker)
    )

    market["DATA"] = pd.to_datetime(
        market["DATA"],
        errors="coerce",
    )

    market["VOLTOT"] = pd.to_numeric(
        market["VOLTOT"],
        errors="coerce",
    )

    market = market[
        market["TICKER"].notna()
        &
        market["DATA"].notna()
    ].copy()

    market = (
        market.groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
        )["VOLTOT"]
        .sum()
    )

    return market


# ============================================================
# 6. HISTÓRICO POR TICKER
# ============================================================

def build_ticker_market_stats(
    market_history: pd.DataFrame,
) -> pd.DataFrame:

    market = validate_market_history(
        market_history
    )

    stats = (
        market.groupby(
            "TICKER",
            as_index=False,
        )
        .agg(
            PRIMEIRA_NEGOCIACAO=(
                "DATA",
                "min",
            ),
            ULTIMA_NEGOCIACAO=(
                "DATA",
                "max",
            ),
            PREGOES_HISTORICOS=(
                "DATA",
                "nunique",
            ),
        )
    )

    return stats


# ============================================================
# 7. HISTÓRICO CONSOLIDADO POR EMPRESA
# ============================================================

def build_company_history(
    ticker_history: pd.DataFrame,
    market_history: pd.DataFrame,
) -> pd.DataFrame:

    history = validate_ticker_history(
        ticker_history
    )

    ticker_stats = (
        build_ticker_market_stats(
            market_history
        )
    )

    merged = history.merge(
        ticker_stats,
        on="TICKER",
        how="left",
        validate="many_to_one",
    )

    resultados = []

    for cd_cvm, group in merged.groupby(
        "CD_CVM"
    ):

        valid = group[
            group[
                "PRIMEIRA_NEGOCIACAO"
            ].notna()
        ].copy()

        if valid.empty:

            resultados.append(
                {
                    "CD_CVM":
                        cd_cvm,

                    "PRIMEIRA_NEGOCIACAO":
                        pd.NaT,

                    "ULTIMA_NEGOCIACAO":
                        pd.NaT,

                    "NUM_TICKERS_HISTORICOS":
                        int(
                            group[
                                "TICKER"
                            ].nunique()
                        ),

                    "TICKERS_HISTORICOS":
                        "|".join(
                            sorted(
                                group[
                                    "TICKER"
                                ]
                                .dropna()
                                .unique()
                            )
                        ),
                }
            )

            continue

        resultados.append(
            {
                "CD_CVM":
                    cd_cvm,

                "PRIMEIRA_NEGOCIACAO":
                    valid[
                        "PRIMEIRA_NEGOCIACAO"
                    ].min(),

                "ULTIMA_NEGOCIACAO":
                    valid[
                        "ULTIMA_NEGOCIACAO"
                    ].max(),

                "NUM_TICKERS_HISTORICOS":
                    int(
                        group[
                            "TICKER"
                        ].nunique()
                    ),

                "TICKERS_HISTORICOS":
                    "|".join(
                        sorted(
                            group[
                                "TICKER"
                            ]
                            .dropna()
                            .unique()
                        )
                    ),
            }
        )

    result = pd.DataFrame(
        resultados
    )

    if result[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado no histórico "
            "consolidado."
        )

    return result


# ============================================================
# 8. LIQUIDEZ POR TICKER
# ============================================================

def build_ticker_liquidity(
    market_history: pd.DataFrame,
    reference_year: int,
) -> pd.DataFrame:

    market = validate_market_history(
        market_history
    )

    market = market[
        market["DATA"].dt.year
        ==
        int(reference_year)
    ].copy()

    if market.empty:

        return pd.DataFrame(
            columns=[
                "TICKER",
                "LIQUIDEZ_MEDIA_DIARIA",
                "PREGOES_LIQUIDEZ",
            ]
        )

    daily = (
        market.groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
        )["VOLTOT"]
        .sum()
    )

    liquidity = (
        daily.groupby(
            "TICKER",
            as_index=False,
        )
        .agg(
            LIQUIDEZ_MEDIA_DIARIA=(
                "VOLTOT",
                "mean",
            ),
            PREGOES_LIQUIDEZ=(
                "DATA",
                "nunique",
            ),
        )
    )

    return liquidity


# ============================================================
# 9. LIQUIDEZ CONSOLIDADA POR EMPRESA
# ============================================================

def build_company_liquidity(
    ticker_history: pd.DataFrame,
    market_history: pd.DataFrame,
    reference_year: int,
) -> pd.DataFrame:

    history = validate_ticker_history(
        ticker_history
    )

    liquidity = build_ticker_liquidity(
        market_history,
        reference_year,
    )

    merged = history.merge(
        liquidity,
        on="TICKER",
        how="left",
        validate="many_to_one",
    )

    resultados = []

    for cd_cvm, group in merged.groupby(
        "CD_CVM"
    ):

        valid = group[
            group[
                "LIQUIDEZ_MEDIA_DIARIA"
            ].notna()
        ].copy()

        if valid.empty:

            resultados.append(
                {
                    "CD_CVM":
                        cd_cvm,

                    "TICKER_LIQUIDEZ":
                        np.nan,

                    "LIQUIDEZ_MEDIA_DIARIA":
                        np.nan,

                    "PREGOES_LIQUIDEZ":
                        0,
                }
            )

            continue

        winner_index = (
            valid[
                "LIQUIDEZ_MEDIA_DIARIA"
            ]
            .idxmax()
        )

        winner = valid.loc[
            winner_index
        ]

        resultados.append(
            {
                "CD_CVM":
                    cd_cvm,

                "TICKER_LIQUIDEZ":
                    winner[
                        "TICKER"
                    ],

                "LIQUIDEZ_MEDIA_DIARIA":
                    float(
                        winner[
                            "LIQUIDEZ_MEDIA_DIARIA"
                        ]
                    ),

                "PREGOES_LIQUIDEZ":
                    int(
                        winner[
                            "PREGOES_LIQUIDEZ"
                        ]
                    ),
            }
        )

    result = pd.DataFrame(
        resultados
    )

    if result[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado na liquidez "
            "consolidada."
        )

    return result


# ============================================================
# 10. MOTIVO DA REPROVAÇÃO
# ============================================================

def rejection_reason(row):

    if pd.isna(
        row["PRIMEIRA_NEGOCIACAO"]
    ):
        return "SEM_HISTORICO_COTAHIST"

    if not bool(
        row["PASSA_10_ANOS"]
    ):
        return "MENOS_DE_10_ANOS"

    if pd.isna(
        row["LIQUIDEZ_MEDIA_DIARIA"]
    ):
        return "SEM_LIQUIDEZ_REFERENCIA"

    if not bool(
        row["PASSA_LIQUIDEZ"]
    ):
        return "LIQUIDEZ_MENOR_6M"

    return ""


# ============================================================
# 11. ENGINE DE INVESTIBILIDADE
# ============================================================

def run_b3_investability(
    quality_approved: pd.DataFrame,
    ticker_history: pd.DataFrame,
    market_history: pd.DataFrame,
    config: InvestabilityConfig,
) -> pd.DataFrame:

    if "CD_CVM" not in quality_approved.columns:

        raise ValueError(
            "Quality Approved sem CD_CVM."
        )

    if quality_approved[
        "CD_CVM"
    ].duplicated().any():

        raise ValueError(
            "CD_CVM duplicado em Quality Approved."
        )

    reference_date = pd.Timestamp(
        config.reference_date
    ).normalize()

    if pd.isna(reference_date):

        raise ValueError(
            "Data de referência inválida."
        )

    history = build_company_history(
        ticker_history,
        market_history,
    )

    liquidity = build_company_liquidity(
        ticker_history,
        market_history,
        config.liquidity_reference_year,
    )

    result = (
        quality_approved
        .copy()
        .merge(
            history,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )
        .merge(
            liquidity,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )
    )

    # ========================================================
    # TEMPO DE NEGOCIAÇÃO
    #
    # Fórmula original:
    # dias / 365.2425
    # ========================================================

    result["ANOS_NEGOCIACAO"] = (
        (
            reference_date
            -
            pd.to_datetime(
                result[
                    "PRIMEIRA_NEGOCIACAO"
                ],
                errors="coerce",
            )
        )
        .dt.days
        /
        DAYS_PER_YEAR
    )

    result["PASSA_10_ANOS"] = (
        result["ANOS_NEGOCIACAO"]
        >=
        config.min_history_years
    )

    # ========================================================
    # LIQUIDEZ
    # ========================================================

    result["PASSA_LIQUIDEZ"] = (
        result[
            "LIQUIDEZ_MEDIA_DIARIA"
        ]
        >=
        config.min_avg_daily_liquidity_brl
    )

    # ========================================================
    # APROVAÇÃO FINAL
    # ========================================================

    result[
        "B3_INVESTABILITY_APPROVED"
    ] = (
        result["PASSA_10_ANOS"]
        &
        result["PASSA_LIQUIDEZ"]
    )

    result[
        "MOTIVO_REPROVACAO_INVESTABILITY"
    ] = result.apply(
        rejection_reason,
        axis=1,
    )

    # ========================================================
    # INTEGRIDADE
    # ========================================================

    approved = result[
        result[
            "B3_INVESTABILITY_APPROVED"
        ]
    ]

    if (
        ~approved[
            "PASSA_10_ANOS"
        ]
    ).any():

        raise RuntimeError(
            "Empresa aprovada com menos "
            "de 10 anos."
        )

    if (
        ~approved[
            "PASSA_LIQUIDEZ"
        ]
    ).any():

        raise RuntimeError(
            "Empresa aprovada abaixo da "
            "liquidez mínima."
        )

    if result[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado após "
            "Investability Engine."
        )

    return result


# ============================================================
# 12. APROVADAS
# ============================================================

def get_investability_approved(
    result: pd.DataFrame,
) -> pd.DataFrame:

    return (
        result[
            result[
                "B3_INVESTABILITY_APPROVED"
            ]
        ]
        .copy()
        .reset_index(drop=True)
    )


# ============================================================
# 13. CONFIGURAÇÃO CONGELADA DO ESTUDO
# ============================================================

def frozen_study_config():

    return InvestabilityConfig(
        reference_date=pd.Timestamp(
            "2025-12-31"
        ),
        liquidity_reference_year=2025,
        min_history_years=10.0,
        min_avg_daily_liquidity_brl=(
            6_000_000.0
        ),
    )


# ============================================================
# 14. CONFIGURAÇÃO LIVE
# ============================================================

def live_config(
    reference_date,
    liquidity_reference_year=None,
):

    reference_date = pd.Timestamp(
        reference_date
    ).normalize()

    if liquidity_reference_year is None:

        liquidity_reference_year = (
            reference_date.year
        )

    return InvestabilityConfig(
        reference_date=reference_date,
        liquidity_reference_year=int(
            liquidity_reference_year
        ),
        min_history_years=10.0,
        min_avg_daily_liquidity_brl=(
            6_000_000.0
        ),
    )


# ============================================================
# 15. SELF TEST
# ============================================================

def _self_test():

    assert MIN_HISTORY_YEARS == 10.0

    assert (
        MIN_AVG_DAILY_LIQUIDITY_BRL
        ==
        6_000_000.0
    )

    assert DAYS_PER_YEAR == 365.2425

    frozen = frozen_study_config()

    assert (
        frozen.reference_date
        ==
        pd.Timestamp("2025-12-31")
    )

    assert (
        frozen.liquidity_reference_year
        ==
        2025
    )

    print(
        "b3_investability_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
