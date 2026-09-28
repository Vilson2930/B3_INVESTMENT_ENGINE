"""
B3 INVESTMENT ENGINE
QUALITY ENGINE V1

Reprodução modular da Célula 18 do estudo original.

OBJETIVO
--------
Transformar os indicadores históricos da Cell17 em:

- QUALITY_SCORE 0–100
- HARD BLOCKS
- CLASSIFICAÇÃO FUNDAMENTAL
- QUALITY GATE

NÃO UTILIZA:
- preço;
- valuation;
- liquidez B3;
- tempo de listagem;
- análise técnica;
- ranking de compra.

FILOSOFIA CONGELADA
-------------------
QUALIDADE PRIMEIRO.

Empresa barata NÃO compensa qualidade ruim.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


QUALITY_GATE = 60.0

FINANCEIROS = {
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
}


# ============================================================
# 1. FUNÇÕES DE SCORE — CELL18
# ============================================================

def score_linear(
    valor,
    ruim,
    excelente,
):
    """
    Quanto MAIOR, melhor.
    """

    if pd.isna(valor):
        return np.nan

    if excelente == ruim:
        return np.nan

    score = (
        (valor - ruim)
        /
        (excelente - ruim)
        * 100
    )

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


def score_inverso(
    valor,
    excelente,
    ruim,
):
    """
    Quanto MENOR, melhor.
    """

    if pd.isna(valor):
        return np.nan

    if ruim == excelente:
        return np.nan

    score = (
        (ruim - valor)
        /
        (ruim - excelente)
        * 100
    )

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


def media_disponivel(
    valores,
    pesos,
):
    """
    Redistribui o peso somente entre métricas disponíveis.

    NaN NÃO é transformado em zero.
    """

    pares = [
        (valor, peso)
        for valor, peso in zip(
            valores,
            pesos,
        )
        if pd.notna(valor)
    ]

    if not pares:
        return np.nan

    soma_pesos = sum(
        peso
        for _, peso in pares
    )

    if soma_pesos <= 0:
        return np.nan

    return float(
        sum(
            valor * peso
            for valor, peso in pares
        )
        /
        soma_pesos
    )


# ============================================================
# 2. PERSISTÊNCIA — TODOS OS MOTORES
# ============================================================

def score_persistencia(row):

    lucro = score_linear(
        row["PCT_LUCRO_POSITIVO"],
        0.50,
        1.00,
    )

    cfo = score_linear(
        row["PCT_CFO_POSITIVO"],
        0.50,
        1.00,
    )

    roe = score_linear(
        row["PCT_ROE_POSITIVO"],
        0.50,
        1.00,
    )

    return media_disponivel(
        [
            lucro,
            cfo,
            roe,
        ],
        [
            0.45,
            0.30,
            0.25,
        ],
    )


# ============================================================
# 3. FINANCEIRO — BANCO
# ============================================================

def score_banco(row):

    rentabilidade = score_linear(
        row["ROE_MEDIANA"],
        0.08,
        0.20,
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.12,
            ),
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.12,
            ),
        ],
        [
            0.65,
            0.35,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            crescimento,
        ],
        [
            0.45,
            0.35,
            0.20,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            np.nan,

        "SCORE_SEGURANCA":
            np.nan,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            np.nan,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 4. FINANCEIRO — SEGUROS
# ============================================================

def score_seguros(row):

    rentabilidade = score_linear(
        row["ROE_MEDIANA"],
        0.10,
        0.25,
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.15,
            ),
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.15,
            ),
        ],
        [
            0.65,
            0.35,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            crescimento,
        ],
        [
            0.45,
            0.35,
            0.20,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            np.nan,

        "SCORE_SEGURANCA":
            np.nan,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            np.nan,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 5. FINANCEIRO ESPECIAL
# ============================================================

def score_financeiro_especial(row):

    rentabilidade = score_linear(
        row["ROE_MEDIANA"],
        0.08,
        0.25,
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.15,
            ),
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.15,
            ),
        ],
        [
            0.65,
            0.35,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            crescimento,
        ],
        [
            0.45,
            0.35,
            0.20,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            np.nan,

        "SCORE_SEGURANCA":
            np.nan,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            np.nan,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 6. COMMODITY
# ============================================================

def score_commodity(row):

    rentabilidade = media_disponivel(
        [
            score_linear(
                row["ROE_MEDIANA"],
                0.08,
                0.20,
            ),
            score_linear(
                row["ROIC_BRUTO_MEDIANA"],
                0.08,
                0.20,
            ),
        ],
        [
            0.40,
            0.60,
        ],
    )

    eficiencia = score_linear(
        row["MARGEM_EBIT_MEDIANA"],
        0.08,
        0.25,
    )

    caixa = media_disponivel(
        [
            score_linear(
                row["CFO_LUCRO_MEDIANA"],
                0.60,
                1.20,
            ),
            score_linear(
                row["PCT_CFO_POSITIVO"],
                0.60,
                1.00,
            ),
        ],
        [
            0.60,
            0.40,
        ],
    )

    seguranca = score_inverso(
        row[
            "DIVIDA_LIQUIDA_EBIT_MEDIANA"
        ],
        1.00,
        4.00,
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.10,
            ),
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.10,
            ),
        ],
        [
            0.50,
            0.50,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            caixa,
            seguranca,
            eficiencia,
            crescimento,
        ],
        [
            0.25,
            0.25,
            0.15,
            0.15,
            0.15,
            0.05,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            caixa,

        "SCORE_SEGURANCA":
            seguranca,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            eficiencia,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 7. UTILITY
# ============================================================

def score_utility(row):

    rentabilidade = media_disponivel(
        [
            score_linear(
                row["ROE_MEDIANA"],
                0.08,
                0.20,
            ),
            score_linear(
                row["ROIC_BRUTO_MEDIANA"],
                0.07,
                0.16,
            ),
        ],
        [
            0.45,
            0.55,
        ],
    )

    eficiencia = score_linear(
        row["MARGEM_EBIT_MEDIANA"],
        0.12,
        0.35,
    )

    caixa = media_disponivel(
        [
            score_linear(
                row["CFO_LUCRO_MEDIANA"],
                0.60,
                1.20,
            ),
            score_linear(
                row["PCT_CFO_POSITIVO"],
                0.70,
                1.00,
            ),
        ],
        [
            0.60,
            0.40,
        ],
    )

    seguranca = score_inverso(
        row[
            "DIVIDA_LIQUIDA_EBIT_MEDIANA"
        ],
        2.00,
        5.00,
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.10,
            ),
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.10,
            ),
        ],
        [
            0.50,
            0.50,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            caixa,
            seguranca,
            eficiencia,
            crescimento,
        ],
        [
            0.25,
            0.25,
            0.15,
            0.15,
            0.10,
            0.10,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            caixa,

        "SCORE_SEGURANCA":
            seguranca,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            eficiencia,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 8. OPERACIONAL / IMOBILIÁRIO / AMBIENTAL
# ============================================================

def score_operacional(row):

    rentabilidade = media_disponivel(
        [
            score_linear(
                row["ROE_MEDIANA"],
                0.08,
                0.20,
            ),
            score_linear(
                row["ROIC_BRUTO_MEDIANA"],
                0.08,
                0.20,
            ),
        ],
        [
            0.40,
            0.60,
        ],
    )

    eficiencia = media_disponivel(
        [
            score_linear(
                row["MARGEM_EBIT_MEDIANA"],
                0.08,
                0.20,
            ),
            score_linear(
                row["MARGEM_LIQUIDA_MEDIANA"],
                0.05,
                0.15,
            ),
        ],
        [
            0.60,
            0.40,
        ],
    )

    caixa = media_disponivel(
        [
            score_linear(
                row["CFO_LUCRO_MEDIANA"],
                0.60,
                1.20,
            ),
            score_linear(
                row["PCT_CFO_POSITIVO"],
                0.60,
                1.00,
            ),
        ],
        [
            0.60,
            0.40,
        ],
    )

    seguranca = media_disponivel(
        [
            score_inverso(
                row[
                    "DIVIDA_LIQUIDA_EBIT_MEDIANA"
                ],
                1.00,
                4.00,
            ),
            score_inverso(
                row[
                    "DIVIDA_BRUTA_PL_MEDIANA"
                ],
                0.30,
                1.50,
            ),
        ],
        [
            0.65,
            0.35,
        ],
    )

    crescimento = media_disponivel(
        [
            score_linear(
                row["CAGR_RECEITA"],
                0.00,
                0.15,
            ),
            score_linear(
                row["CAGR_LUCRO"],
                0.00,
                0.15,
            ),
        ],
        [
            0.45,
            0.55,
        ],
    )

    persistencia = score_persistencia(
        row
    )

    quality = media_disponivel(
        [
            rentabilidade,
            persistencia,
            caixa,
            seguranca,
            crescimento,
            eficiencia,
        ],
        [
            0.25,
            0.20,
            0.15,
            0.15,
            0.15,
            0.10,
        ],
    )

    return {
        "SCORE_RENTABILIDADE":
            rentabilidade,

        "SCORE_PERSISTENCIA":
            persistencia,

        "SCORE_CAIXA":
            caixa,

        "SCORE_SEGURANCA":
            seguranca,

        "SCORE_CRESCIMENTO":
            crescimento,

        "SCORE_EFICIENCIA":
            eficiencia,

        "QUALITY_SCORE":
            quality,
    }


# ============================================================
# 9. DESPACHO POR MOTOR
# ============================================================

def calcular_scores(row):

    motor = row["MOTOR_FINAL"]

    if motor == "FINANCEIRO_BANCO":
        return score_banco(row)

    if motor == "FINANCEIRO_SEGUROS":
        return score_seguros(row)

    if motor == "FINANCEIRO_ESPECIAL":
        return score_financeiro_especial(row)

    if motor == "COMMODITY":
        return score_commodity(row)

    if motor == "UTILITY":
        return score_utility(row)

    if motor in {
        "OPERACIONAL",
        "IMOBILIARIO",
        "AMBIENTAL_RESIDUOS",
    }:
        return score_operacional(row)

    return {
        "SCORE_RENTABILIDADE":
            np.nan,

        "SCORE_PERSISTENCIA":
            np.nan,

        "SCORE_CAIXA":
            np.nan,

        "SCORE_SEGURANCA":
            np.nan,

        "SCORE_CRESCIMENTO":
            np.nan,

        "SCORE_EFICIENCIA":
            np.nan,

        "QUALITY_SCORE":
            np.nan,
    }


# ============================================================
# 10. HARD BLOCKS — CELL18
# ============================================================

def calcular_hard_blocks(row):

    motivos = []

    motor = row["MOTOR_FINAL"]

    if not bool(
        row["ELEGIVEL_DADOS_QUALITY"]
    ):
        motivos.append(
            "DADOS_INSUFICIENTES"
        )

    if motor == "AUDITAR":
        motivos.append(
            "MOTOR_ECONOMICO_NAO_RESOLVIDO"
        )

    pct_lucro = row[
        "PCT_LUCRO_POSITIVO"
    ]

    if (
        pd.notna(pct_lucro)
        and pct_lucro < 0.60
    ):
        motivos.append(
            "LUCRO_RECORRENTEMENTE_NEGATIVO"
        )

    roe = row["ROE_MEDIANA"]

    if (
        pd.notna(roe)
        and roe <= 0
    ):
        motivos.append(
            "RENTABILIDADE_PATRIMONIAL_NAO_POSITIVA"
        )

    if (
        motor not in FINANCEIROS
        and motor != "AUDITAR"
    ):

        roic = row[
            "ROIC_BRUTO_MEDIANA"
        ]

        if (
            pd.notna(roic)
            and roic <= 0
        ):
            motivos.append(
                "RETORNO_OPERACIONAL_NAO_POSITIVO"
            )

        pct_cfo = row[
            "PCT_CFO_POSITIVO"
        ]

        if (
            pd.notna(pct_cfo)
            and pct_cfo < 0.60
        ):
            motivos.append(
                "CAIXA_OPERACIONAL_FRACO"
            )

        divida = row[
            "DIVIDA_LIQUIDA_EBIT_MEDIANA"
        ]

        limite = (
            7.0
            if motor == "UTILITY"
            else 6.0
        )

        if (
            pd.notna(divida)
            and divida > limite
        ):
            motivos.append(
                "ALAVANCAGEM_EXTREMA"
            )

    return motivos


# ============================================================
# 11. CLASSIFICAÇÃO
# ============================================================

def classificar_quality(
    score,
    hard_block,
):

    if hard_block:
        return "REPROVADA_HARD_BLOCK"

    if pd.isna(score):
        return "SEM_SCORE"

    if score >= 80:
        return "QUALIDADE_EXCEPCIONAL"

    if score >= 70:
        return "QUALIDADE_ALTA"

    if score >= 60:
        return "QUALIDADE_APROVADA"

    if score >= 50:
        return "QUALIDADE_INTERMEDIARIA"

    return "QUALIDADE_INSUFICIENTE"


# ============================================================
# 12. COLUNAS OBRIGATÓRIAS
# ============================================================

REQUIRED_COLUMNS = {
    "CD_CVM",
    "DENOM_CIA_ATUAL",
    "MOTOR_FINAL",
    "ELEGIVEL_DADOS_QUALITY",
    "PCT_LUCRO_POSITIVO",
    "PCT_CFO_POSITIVO",
    "PCT_ROE_POSITIVO",
    "ROE_MEDIANA",
    "ROIC_BRUTO_MEDIANA",
    "MARGEM_EBIT_MEDIANA",
    "MARGEM_LIQUIDA_MEDIANA",
    "CFO_LUCRO_MEDIANA",
    "DIVIDA_BRUTA_PL_MEDIANA",
    "DIVIDA_LIQUIDA_EBIT_MEDIANA",
    "CAGR_RECEITA",
    "CAGR_LUCRO",
}


# ============================================================
# 13. QUALITY ENGINE V1
# ============================================================

def run_quality_engine(
    company_summary: pd.DataFrame,
) -> pd.DataFrame:

    missing = (
        REQUIRED_COLUMNS
        - set(company_summary.columns)
    )

    if missing:

        raise ValueError(
            "Quality Engine sem colunas obrigatórias: "
            + ", ".join(
                sorted(missing)
            )
        )

    empresa = company_summary.copy()

    if empresa["CD_CVM"].duplicated().any():

        raise ValueError(
            "CD_CVM duplicado antes do Quality Engine."
        )

    # ========================================================
    # SCORES
    # ========================================================

    scores = empresa.apply(
        calcular_scores,
        axis=1,
    )

    scores_df = pd.DataFrame(
        scores.tolist(),
        index=empresa.index,
    )

    for coluna in scores_df.columns:

        empresa[coluna] = (
            scores_df[coluna]
        )

    # ========================================================
    # HARD BLOCKS
    # ========================================================

    hard_blocks = empresa.apply(
        calcular_hard_blocks,
        axis=1,
    )

    empresa[
        "HARD_BLOCK_MOTIVOS"
    ] = hard_blocks.apply(
        lambda motivos:
        "|".join(motivos)
    )

    empresa["HARD_BLOCK"] = (
        hard_blocks.apply(
            lambda motivos:
            len(motivos) > 0
        )
    )

    # ========================================================
    # CLASSIFICAÇÃO
    # ========================================================

    empresa[
        "CLASSIFICACAO_QUALITY"
    ] = empresa.apply(
        lambda row:
        classificar_quality(
            row["QUALITY_SCORE"],
            row["HARD_BLOCK"],
        ),
        axis=1,
    )

    # ========================================================
    # QUALITY GATE
    # ========================================================

    empresa["QUALITY_APPROVED"] = (
        (~empresa["HARD_BLOCK"])
        &
        (
            empresa["QUALITY_SCORE"]
            >= QUALITY_GATE
        )
    )

    # ========================================================
    # INTEGRIDADE
    # ========================================================

    if (
        empresa.loc[
            empresa["QUALITY_APPROVED"],
            "HARD_BLOCK",
        ].any()
    ):

        raise RuntimeError(
            "Empresa com HARD BLOCK foi aprovada."
        )

    if (
        empresa.loc[
            empresa["QUALITY_APPROVED"],
            "QUALITY_SCORE",
        ]
        < QUALITY_GATE
    ).any():

        raise RuntimeError(
            "Empresa abaixo do Quality Gate foi aprovada."
        )

    if empresa["CD_CVM"].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado após Quality Engine."
        )

    return empresa


# ============================================================
# 14. SEPARAÇÃO DOS RESULTADOS
# ============================================================

def split_quality_results(
    quality_result: pd.DataFrame,
):

    approved = (
        quality_result[
            quality_result[
                "QUALITY_APPROVED"
            ]
        ]
        .copy()
        .reset_index(drop=True)
    )

    blocked = (
        quality_result[
            quality_result[
                "HARD_BLOCK"
            ]
        ]
        .copy()
        .reset_index(drop=True)
    )

    return approved, blocked


# ============================================================
# 15. SELF TEST
# ============================================================

def _self_test():

    assert score_linear(
        0.50,
        0.50,
        1.00,
    ) == 0.0

    assert score_linear(
        1.00,
        0.50,
        1.00,
    ) == 100.0

    assert score_inverso(
        1.00,
        1.00,
        4.00,
    ) == 100.0

    assert score_inverso(
        4.00,
        1.00,
        4.00,
    ) == 0.0

    assert (
        media_disponivel(
            [
                100.0,
                np.nan,
                50.0,
            ],
            [
                0.50,
                0.25,
                0.25,
            ],
        )
        ==
        (
            100.0 * 0.50
            +
            50.0 * 0.25
        )
        /
        0.75
    )

    assert (
        classificar_quality(
            80.0,
            False,
        )
        ==
        "QUALIDADE_EXCEPCIONAL"
    )

    assert (
        classificar_quality(
            60.0,
            False,
        )
        ==
        "QUALIDADE_APROVADA"
    )

    assert (
        classificar_quality(
            99.0,
            True,
        )
        ==
        "REPROVADA_HARD_BLOCK"
    )

    print(
        "quality_engine_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
