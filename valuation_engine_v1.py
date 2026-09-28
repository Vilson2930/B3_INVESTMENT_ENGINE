"""
B3 INVESTMENT ENGINE
VALUATION ENGINE V1

Reprodução modular da metodologia final:
Cell33 + Cell33B + Cell33C.

ARQUITETURA
-----------
Quality aprovado
    ↓
Investibilidade B3 aprovada
    ↓
Valuation por família econômica

FAMÍLIAS
--------
COMMODITY
FINANCEIRO
OPERACIONAL
UTILITY

REGRAS
------
COMMODITY:
    50% P/L normalizado
    50% EV/EBIT normalizado

OPERACIONAL:
    50% P/L
    50% EV/EBIT

UTILITY:
    50% P/L
    50% EV/EBIT

FINANCEIRO:
    45% P/L
    35% P/VP ajustado pelo ROE
    20% ROE histórico

Nenhum valuation resgata empresa reprovada em Quality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================
# 1. FAMÍLIAS
# ============================================================

VALID_FAMILIES = {
    "COMMODITY",
    "FINANCEIRO",
    "OPERACIONAL",
    "UTILITY",
}


# ============================================================
# 2. SCORE PERCENTIL — MENOR É MELHOR
# ============================================================

def score_menor_melhor(
    serie: pd.Series,
) -> pd.Series:

    s = pd.to_numeric(
        serie,
        errors="coerce",
    )

    resultado = pd.Series(
        np.nan,
        index=s.index,
        dtype=float,
    )

    validos = (
        s.replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    n = len(validos)

    if n == 0:
        return resultado

    if n == 1:

        resultado.loc[
            validos.index
        ] = 50.0

        return resultado

    ranks = validos.rank(
        method="average",
        ascending=True,
    )

    scores = (
        100.0
        *
        (n - ranks)
        /
        (n - 1)
    )

    resultado.loc[
        validos.index
    ] = scores

    return resultado


# ============================================================
# 3. SCORE PERCENTIL — MAIOR É MELHOR
# ============================================================

def score_maior_melhor(
    serie: pd.Series,
) -> pd.Series:

    s = pd.to_numeric(
        serie,
        errors="coerce",
    )

    resultado = pd.Series(
        np.nan,
        index=s.index,
        dtype=float,
    )

    validos = (
        s.replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    n = len(validos)

    if n == 0:
        return resultado

    if n == 1:

        resultado.loc[
            validos.index
        ] = 50.0

        return resultado

    ranks = validos.rank(
        method="average",
        ascending=True,
    )

    scores = (
        100.0
        *
        (ranks - 1)
        /
        (n - 1)
    )

    resultado.loc[
        validos.index
    ] = scores

    return resultado


# ============================================================
# 4. CLASSIFICAÇÃO
# ============================================================

def classificar_valuation(score):

    if pd.isna(score):
        return "PENDENTE"

    if score >= 80:
        return "MUITO_ATRATIVO"

    if score >= 65:
        return "ATRATIVO"

    if score >= 45:
        return "NEUTRO"

    if score >= 25:
        return "EXIGENTE"

    return "MUITO_EXIGENTE"


# ============================================================
# 5. VALIDAÇÃO
# ============================================================

REQUIRED_COLUMNS = {
    "CD_CVM",
    "TICKER_VALUATION",
    "QUALITY_SCORE",
    "FAMILIA_VALUATION",
    "PL_ATUAL",
    "P_VP_ATUAL",
    "EV_EBIT_ATUAL",
    "MARKET_CAP_ATUAL",
}


def validate_valuation_base(
    valuation_base: pd.DataFrame,
) -> None:

    missing = (
        REQUIRED_COLUMNS
        - set(valuation_base.columns)
    )

    if missing:

        raise ValueError(
            "Base de valuation sem colunas "
            "obrigatórias: "
            + ", ".join(sorted(missing))
        )

    if valuation_base.empty:

        raise ValueError(
            "Base de valuation vazia."
        )

    if valuation_base[
        "CD_CVM"
    ].duplicated().any():

        raise ValueError(
            "CD_CVM duplicado na base "
            "de valuation."
        )


# ============================================================
# 6. PREPARAÇÃO
# ============================================================

def prepare_base(
    valuation_base: pd.DataFrame,
) -> pd.DataFrame:

    validate_valuation_base(
        valuation_base
    )

    df = valuation_base.copy()

    df["TICKER_VALUATION"] = (
        df["TICKER_VALUATION"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["FAMILIA_VALUATION"] = (
        df["FAMILIA_VALUATION"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    invalid = set(
        df[
            "FAMILIA_VALUATION"
        ].dropna().unique()
    ) - VALID_FAMILIES

    if invalid:

        raise ValueError(
            "Famílias de valuation "
            "não reconhecidas: "
            + ", ".join(
                sorted(invalid)
            )
        )

    numeric_candidates = [
        "QUALITY_SCORE",
        "PL_ATUAL",
        "P_VP_ATUAL",
        "EV_EBIT_ATUAL",
        "MARKET_CAP_ATUAL",
        "DIVIDA_LIQUIDA_R",
        "ROE_HISTORICO_VALUATION",
        "PL_NORMALIZADO_C25",
        "EV_EBIT_NORMALIZADO_C25_CORRETO",
        "MARKET_CAP_ANTIGO_CORRETO",
    ]

    for col in numeric_candidates:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

    return df


# ============================================================
# 7. P/VP AJUSTADO POR ROE — FINANCEIROS
# ============================================================

def build_financial_relative_valuation(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    df["PVP_ROE"] = np.nan

    mask_fin = (
        df["FAMILIA_VALUATION"]
        .eq("FINANCEIRO")
    )

    if (
        "ROE_HISTORICO_VALUATION"
        not in df.columns
    ):

        df[
            "ROE_HISTORICO_VALUATION"
        ] = np.nan

    mask = (
        mask_fin
        &
        df["P_VP_ATUAL"].gt(0)
        &
        df[
            "ROE_HISTORICO_VALUATION"
        ].gt(0)
    )

    df.loc[
        mask,
        "PVP_ROE",
    ] = (
        df.loc[
            mask,
            "P_VP_ATUAL",
        ]
        /
        df.loc[
            mask,
            "ROE_HISTORICO_VALUATION",
        ]
    )

    return df


# ============================================================
# 8. COMMODITY — CORREÇÃO CELL33B/CELL33C
# ============================================================

def build_commodity_normalized_multiples(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    required = [
        "PL_NORMALIZADO_C25",
        "EV_EBIT_NORMALIZADO_C25_CORRETO",
        "MARKET_CAP_ANTIGO_CORRETO",
        "DIVIDA_LIQUIDA_R",
    ]

    for col in required:

        if col not in df.columns:
            df[col] = np.nan

    mask_commodity = (
        df["FAMILIA_VALUATION"]
        .eq("COMMODITY")
    )

    # ========================================================
    # FATOR DE MARKET CAP
    #
    # Cell33B:
    # Market Cap atual / Market Cap antigo.
    # ========================================================

    df[
        "FATOR_MARKET_CAP"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df["MARKET_CAP_ATUAL"].gt(0)
        &
        df[
            "MARKET_CAP_ANTIGO_CORRETO"
        ].gt(0)
    )

    df.loc[
        mask,
        "FATOR_MARKET_CAP",
    ] = (
        df.loc[
            mask,
            "MARKET_CAP_ATUAL",
        ]
        /
        df.loc[
            mask,
            "MARKET_CAP_ANTIGO_CORRETO",
        ]
    )

    # ========================================================
    # P/L NORMALIZADO ATUALIZADO
    #
    # Cell33B:
    #
    # P/L novo =
    # P/L normalizado antigo
    # × MarketCap atual / MarketCap antigo
    # ========================================================

    df[
        "PL_COMMODITY_CORRIGIDO"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df[
            "PL_NORMALIZADO_C25"
        ].gt(0)
        &
        df[
            "FATOR_MARKET_CAP"
        ].gt(0)
    )

    df.loc[
        mask,
        "PL_COMMODITY_CORRIGIDO",
    ] = (
        df.loc[
            mask,
            "PL_NORMALIZADO_C25",
        ]
        *
        df.loc[
            mask,
            "FATOR_MARKET_CAP",
        ]
    )

    # ========================================================
    # EV ANTIGO CORRETO — CELL33C
    #
    # EV antigo =
    # Market Cap antigo + Dívida Líquida
    # ========================================================

    df[
        "EV_ANTIGO_CORRETO"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df[
            "MARKET_CAP_ANTIGO_CORRETO"
        ].notna()
        &
        df[
            "DIVIDA_LIQUIDA_R"
        ].notna()
    )

    df.loc[
        mask,
        "EV_ANTIGO_CORRETO",
    ] = (
        df.loc[
            mask,
            "MARKET_CAP_ANTIGO_CORRETO",
        ]
        +
        df.loc[
            mask,
            "DIVIDA_LIQUIDA_R",
        ]
    )

    # ========================================================
    # EV ATUAL CORRETO
    #
    # EV atual =
    # Market Cap atual + Dívida Líquida
    # ========================================================

    df[
        "EV_ATUAL_CORRETO"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df[
            "MARKET_CAP_ATUAL"
        ].notna()
        &
        df[
            "DIVIDA_LIQUIDA_R"
        ].notna()
    )

    df.loc[
        mask,
        "EV_ATUAL_CORRETO",
    ] = (
        df.loc[
            mask,
            "MARKET_CAP_ATUAL",
        ]
        +
        df.loc[
            mask,
            "DIVIDA_LIQUIDA_R",
        ]
    )

    # ========================================================
    # FATOR EV — CELL33C
    # ========================================================

    df[
        "FATOR_EV_CORRETO"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df[
            "EV_ANTIGO_CORRETO"
        ].gt(0)
        &
        df[
            "EV_ATUAL_CORRETO"
        ].gt(0)
    )

    df.loc[
        mask,
        "FATOR_EV_CORRETO",
    ] = (
        df.loc[
            mask,
            "EV_ATUAL_CORRETO",
        ]
        /
        df.loc[
            mask,
            "EV_ANTIGO_CORRETO",
        ]
    )

    # ========================================================
    # EV/EBIT NORMALIZADO FINAL — CELL33C
    # ========================================================

    df[
        "EV_EBIT_COMMODITY_FINAL"
    ] = np.nan

    mask = (
        mask_commodity
        &
        df[
            "EV_EBIT_NORMALIZADO_C25_CORRETO"
        ].gt(0)
        &
        df[
            "FATOR_EV_CORRETO"
        ].gt(0)
    )

    df.loc[
        mask,
        "EV_EBIT_COMMODITY_FINAL",
    ] = (
        df.loc[
            mask,
            "EV_EBIT_NORMALIZADO_C25_CORRETO",
        ]
        *
        df.loc[
            mask,
            "FATOR_EV_CORRETO",
        ]
    )

    return df


# ============================================================
# 9. ENGINE DE VALUATION
# ============================================================

def run_valuation_engine(
    valuation_base: pd.DataFrame,
) -> pd.DataFrame:

    df = prepare_base(
        valuation_base
    )

    df = build_financial_relative_valuation(
        df
    )

    df = build_commodity_normalized_multiples(
        df
    )

    # ========================================================
    # COLUNAS DE SCORE
    # ========================================================

    df["SCORE_PL"] = np.nan
    df["SCORE_EV_EBIT"] = np.nan
    df["SCORE_PVP_ROE"] = np.nan
    df["SCORE_ROE_FIN"] = np.nan
    df["VALUATION_SCORE"] = np.nan

    # ========================================================
    # COMMODITY
    #
    # 50% P/L normalizado
    # 50% EV/EBIT normalizado
    #
    # Exige as duas dimensões.
    # ========================================================

    mask = (
        df["FAMILIA_VALUATION"]
        .eq("COMMODITY")
    )

    idx = df.index[mask]

    df.loc[
        idx,
        "SCORE_PL",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "PL_COMMODITY_CORRIGIDO",
        ]
    )

    df.loc[
        idx,
        "SCORE_EV_EBIT",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "EV_EBIT_COMMODITY_FINAL",
        ]
    )

    valid = (
        mask
        &
        df["SCORE_PL"].notna()
        &
        df["SCORE_EV_EBIT"].notna()
    )

    df.loc[
        valid,
        "VALUATION_SCORE",
    ] = (
        0.50
        *
        df.loc[
            valid,
            "SCORE_PL",
        ]
        +
        0.50
        *
        df.loc[
            valid,
            "SCORE_EV_EBIT",
        ]
    )

    # ========================================================
    # OPERACIONAL
    #
    # 50% P/L
    # 50% EV/EBIT
    # ========================================================

    mask = (
        df["FAMILIA_VALUATION"]
        .eq("OPERACIONAL")
    )

    idx = df.index[mask]

    df.loc[
        idx,
        "SCORE_PL",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "PL_ATUAL",
        ]
    )

    df.loc[
        idx,
        "SCORE_EV_EBIT",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "EV_EBIT_ATUAL",
        ]
    )

    valid = (
        mask
        &
        df["SCORE_PL"].notna()
        &
        df["SCORE_EV_EBIT"].notna()
    )

    df.loc[
        valid,
        "VALUATION_SCORE",
    ] = (
        0.50
        *
        df.loc[
            valid,
            "SCORE_PL",
        ]
        +
        0.50
        *
        df.loc[
            valid,
            "SCORE_EV_EBIT",
        ]
    )

    # ========================================================
    # UTILITY
    #
    # 50% P/L
    # 50% EV/EBIT
    # ========================================================

    mask = (
        df["FAMILIA_VALUATION"]
        .eq("UTILITY")
    )

    idx = df.index[mask]

    df.loc[
        idx,
        "SCORE_PL",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "PL_ATUAL",
        ]
    )

    df.loc[
        idx,
        "SCORE_EV_EBIT",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "EV_EBIT_ATUAL",
        ]
    )

    valid = (
        mask
        &
        df["SCORE_PL"].notna()
        &
        df["SCORE_EV_EBIT"].notna()
    )

    df.loc[
        valid,
        "VALUATION_SCORE",
    ] = (
        0.50
        *
        df.loc[
            valid,
            "SCORE_PL",
        ]
        +
        0.50
        *
        df.loc[
            valid,
            "SCORE_EV_EBIT",
        ]
    )

    # ========================================================
    # FINANCEIRO
    #
    # 45% P/L
    # 35% P/VP ajustado pelo ROE
    # 20% ROE histórico
    #
    # Exige as três dimensões.
    # ========================================================

    mask = (
        df["FAMILIA_VALUATION"]
        .eq("FINANCEIRO")
    )

    idx = df.index[mask]

    df.loc[
        idx,
        "SCORE_PL",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "PL_ATUAL",
        ]
    )

    df.loc[
        idx,
        "SCORE_PVP_ROE",
    ] = score_menor_melhor(
        df.loc[
            idx,
            "PVP_ROE",
        ]
    )

    df.loc[
        idx,
        "SCORE_ROE_FIN",
    ] = score_maior_melhor(
        df.loc[
            idx,
            "ROE_HISTORICO_VALUATION",
        ]
    )

    valid = (
        mask
        &
        df["SCORE_PL"].notna()
        &
        df["SCORE_PVP_ROE"].notna()
        &
        df["SCORE_ROE_FIN"].notna()
    )

    df.loc[
        valid,
        "VALUATION_SCORE",
    ] = (
        0.45
        *
        df.loc[
            valid,
            "SCORE_PL",
        ]
        +
        0.35
        *
        df.loc[
            valid,
            "SCORE_PVP_ROE",
        ]
        +
        0.20
        *
        df.loc[
            valid,
            "SCORE_ROE_FIN",
        ]
    )

    # ========================================================
    # DISPONIBILIDADE
    # ========================================================

    df[
        "VALUATION_DISPONIVEL"
    ] = (
        df[
            "VALUATION_SCORE"
        ].notna()
    )

    # ========================================================
    # CLASSIFICAÇÃO
    # ========================================================

    df[
        "CLASSIFICACAO_VALUATION"
    ] = (
        df[
            "VALUATION_SCORE"
        ]
        .apply(
            classificar_valuation
        )
    )

    # ========================================================
    # RANK POR FAMÍLIA
    # ========================================================

    df[
        "RANK_VALUATION_FAMILIA"
    ] = np.nan

    for familia in [
        "COMMODITY",
        "FINANCEIRO",
        "OPERACIONAL",
        "UTILITY",
    ]:

        family_mask = (
            df[
                "FAMILIA_VALUATION"
            ].eq(familia)
            &
            df[
                "VALUATION_SCORE"
            ].notna()
        )

        df.loc[
            family_mask,
            "RANK_VALUATION_FAMILIA",
        ] = (
            df.loc[
                family_mask,
                "VALUATION_SCORE",
            ]
            .rank(
                method="min",
                ascending=False,
            )
        )

    # ========================================================
    # SANIDADE
    # ========================================================

    scores = df[
        "VALUATION_SCORE"
    ].dropna()

    if (
        (scores < 0)
        |
        (scores > 100)
    ).any():

        raise RuntimeError(
            "Valuation Score fora do "
            "intervalo 0–100."
        )

    commodity_ev = (
        df.loc[
            df[
                "FAMILIA_VALUATION"
            ].eq("COMMODITY"),
            "EV_EBIT_COMMODITY_FINAL",
        ]
        .dropna()
    )

    # Cell33C utilizou 500x apenas como
    # limite amplo de sanidade/unidade.

    if (
        commodity_ev.abs() > 500
    ).any():

        raise RuntimeError(
            "EV/EBIT commodity acima de "
            "500x. Possível erro de unidade."
        )

    if df[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado após "
            "Valuation Engine."
        )

    return df


# ============================================================
# 10. VALUATIONS DISPONÍVEIS
# ============================================================

def get_available_valuations(
    result: pd.DataFrame,
) -> pd.DataFrame:

    return (
        result[
            result[
                "VALUATION_DISPONIVEL"
            ]
        ]
        .copy()
        .reset_index(drop=True)
    )


# ============================================================
# 11. PENDENTES
# ============================================================

def get_pending_valuations(
    result: pd.DataFrame,
) -> pd.DataFrame:

    return (
        result[
            ~result[
                "VALUATION_DISPONIVEL"
            ]
        ]
        .copy()
        .reset_index(drop=True)
    )


# ============================================================
# 12. SELF TEST
# ============================================================

def _self_test():

    serie = pd.Series(
        [1.0, 2.0, 3.0]
    )

    menor = score_menor_melhor(
        serie
    )

    assert menor.iloc[0] == 100.0
    assert menor.iloc[1] == 50.0
    assert menor.iloc[2] == 0.0

    maior = score_maior_melhor(
        serie
    )

    assert maior.iloc[0] == 0.0
    assert maior.iloc[1] == 50.0
    assert maior.iloc[2] == 100.0

    assert (
        classificar_valuation(80)
        ==
        "MUITO_ATRATIVO"
    )

    assert (
        classificar_valuation(65)
        ==
        "ATRATIVO"
    )

    assert (
        classificar_valuation(45)
        ==
        "NEUTRO"
    )

    assert (
        classificar_valuation(25)
        ==
        "EXIGENTE"
    )

    assert (
        classificar_valuation(np.nan)
        ==
        "PENDENTE"
    )

    print(
        "valuation_engine_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
