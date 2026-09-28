"""
B3 INVESTMENT ENGINE
FUNDAMENTAL INDICATORS V1

Reprodução modular da Célula 17 do estudo original.

OBJETIVO
--------
Transformar a base contábil histórica em indicadores
econômicos de qualidade.

NÃO:
- calcula Quality Score;
- cria ranking;
- calcula valuation;
- aplica liquidez B3;
- aplica tempo mínimo de negociação.

METODOLOGIA V1 CONGELADA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


FINANCEIROS = {
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
}


# ============================================================
# 1. FUNÇÕES ORIGINAIS
# ============================================================

def divisao_segura(num, den):

    num = pd.to_numeric(
        num,
        errors="coerce",
    )

    den = pd.to_numeric(
        den,
        errors="coerce",
    )

    return np.where(
        den.notna()
        &
        num.notna()
        &
        (den != 0),
        num / den,
        np.nan,
    )


def cagr_seguro(inicial, final, anos):

    if (
        pd.isna(inicial)
        or pd.isna(final)
        or anos <= 0
        or inicial <= 0
        or final <= 0
    ):
        return np.nan

    return (
        (final / inicial)
        ** (1 / anos)
        - 1
    )


# ============================================================
# 2. VALIDAÇÃO DA BASE
# ============================================================

REQUIRED_COLUMNS = {
    "CD_CVM",
    "ANO",
    "DENOM_CIA_ATUAL",
    "MOTOR_FINAL",
    "ELEGIVEL_DADOS_QUALITY",
    "PATRIMONIO_LIQUIDO",
    "ATIVO_TOTAL",
    "DIVIDA_BRUTA",
    "DIVIDA_LIQUIDA",
    "CAIXA",
    "RECEITA",
    "EBIT",
    "LUCRO_LIQUIDO",
    "CFO",
}


def validar_base(base: pd.DataFrame) -> None:

    missing = (
        REQUIRED_COLUMNS
        - set(base.columns)
    )

    if missing:

        raise ValueError(
            "Base fundamental sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    if base.empty:

        raise ValueError(
            "Base fundamental vazia."
        )

    if base[
        ["CD_CVM", "ANO"]
    ].duplicated().any():

        raise ValueError(
            "Duplicidade CD_CVM + ANO "
            "na base fundamental."
        )


# ============================================================
# 3. INDICADORES ANUAIS — CELL17
# ============================================================

def build_raw_indicators(
    fundamental_base: pd.DataFrame,
) -> pd.DataFrame:

    validar_base(fundamental_base)

    base = fundamental_base.copy()

    base = base.sort_values(
        ["CD_CVM", "ANO"]
    ).reset_index(drop=True)

    base["EH_FINANCEIRO"] = (
        base["MOTOR_FINAL"]
        .isin(FINANCEIROS)
    )

    # ========================================================
    # MÉDIAS DE BALANÇO
    # ========================================================

    base["PL_ANTERIOR"] = (
        base.groupby("CD_CVM")[
            "PATRIMONIO_LIQUIDO"
        ].shift(1)
    )

    base["ATIVO_ANTERIOR"] = (
        base.groupby("CD_CVM")[
            "ATIVO_TOTAL"
        ].shift(1)
    )

    base["PL_MEDIO"] = (
        (
            base["PATRIMONIO_LIQUIDO"]
            +
            base["PL_ANTERIOR"]
        )
        / 2
    )

    # ========================================================
    # ROE
    #
    # Lucro Líquido / PL médio.
    # Exige PL médio positivo.
    # ========================================================

    base["ROE"] = np.where(
        base["PL_MEDIO"] > 0,
        divisao_segura(
            base["LUCRO_LIQUIDO"],
            base["PL_MEDIO"],
        ),
        np.nan,
    )

    # ========================================================
    # CAPITAL INVESTIDO
    #
    # PL + Dívida Bruta - Caixa
    # ========================================================

    base["CAPITAL_INVESTIDO"] = (
        base["PATRIMONIO_LIQUIDO"]
        +
        base["DIVIDA_BRUTA"]
        -
        base["CAIXA"]
    )

    base["CI_ANTERIOR"] = (
        base.groupby("CD_CVM")[
            "CAPITAL_INVESTIDO"
        ].shift(1)
    )

    base["CI_MEDIO"] = (
        (
            base["CAPITAL_INVESTIDO"]
            +
            base["CI_ANTERIOR"]
        )
        / 2
    )

    # ========================================================
    # ROIC BRUTO
    #
    # EBIT / Capital Investido Médio.
    # Não aplicado aos financeiros.
    # ========================================================

    base["ROIC_BRUTO"] = np.where(
        (
            ~base["EH_FINANCEIRO"]
        )
        &
        (
            base["CI_MEDIO"] > 0
        ),
        divisao_segura(
            base["EBIT"],
            base["CI_MEDIO"],
        ),
        np.nan,
    )

    # ========================================================
    # MARGENS
    # ========================================================

    base["MARGEM_EBIT"] = np.where(
        ~base["EH_FINANCEIRO"],
        divisao_segura(
            base["EBIT"],
            base["RECEITA"],
        ),
        np.nan,
    )

    base["MARGEM_LIQUIDA"] = np.where(
        ~base["EH_FINANCEIRO"],
        divisao_segura(
            base["LUCRO_LIQUIDO"],
            base["RECEITA"],
        ),
        np.nan,
    )

    # ========================================================
    # QUALIDADE DE CAIXA
    #
    # CFO/Lucro somente quando lucro > 0.
    # ========================================================

    base["CFO_LUCRO"] = np.where(
        base["LUCRO_LIQUIDO"] > 0,
        divisao_segura(
            base["CFO"],
            base["LUCRO_LIQUIDO"],
        ),
        np.nan,
    )

    base["CFO_RECEITA"] = np.where(
        ~base["EH_FINANCEIRO"],
        divisao_segura(
            base["CFO"],
            base["RECEITA"],
        ),
        np.nan,
    )

    # ========================================================
    # ENDIVIDAMENTO
    # ========================================================

    base["DIVIDA_BRUTA_PL"] = np.where(
        (
            ~base["EH_FINANCEIRO"]
        )
        &
        (
            base["PATRIMONIO_LIQUIDO"] > 0
        ),
        divisao_segura(
            base["DIVIDA_BRUTA"],
            base["PATRIMONIO_LIQUIDO"],
        ),
        np.nan,
    )

    base["DIVIDA_LIQUIDA_EBIT"] = np.where(
        (
            ~base["EH_FINANCEIRO"]
        )
        &
        (
            base["EBIT"] > 0
        ),
        divisao_segura(
            base["DIVIDA_LIQUIDA"],
            base["EBIT"],
        ),
        np.nan,
    )

    # ========================================================
    # CRESCIMENTO ANUAL
    # ========================================================

    base["RECEITA_ANTERIOR"] = (
        base.groupby("CD_CVM")[
            "RECEITA"
        ].shift(1)
    )

    base["LUCRO_ANTERIOR"] = (
        base.groupby("CD_CVM")[
            "LUCRO_LIQUIDO"
        ].shift(1)
    )

    base["CRESC_RECEITA_YOY"] = np.where(
        (
            base["RECEITA"] > 0
        )
        &
        (
            base["RECEITA_ANTERIOR"] > 0
        ),
        (
            base["RECEITA"]
            /
            base["RECEITA_ANTERIOR"]
            - 1
        ),
        np.nan,
    )

    base["CRESC_LUCRO_YOY"] = np.where(
        (
            base["LUCRO_LIQUIDO"] > 0
        )
        &
        (
            base["LUCRO_ANTERIOR"] > 0
        ),
        (
            base["LUCRO_LIQUIDO"]
            /
            base["LUCRO_ANTERIOR"]
            - 1
        ),
        np.nan,
    )

    # ========================================================
    # FLAGS DE PERSISTÊNCIA
    # ========================================================

    base["LUCRO_POSITIVO"] = (
        base["LUCRO_LIQUIDO"] > 0
    )

    base["CFO_POSITIVO"] = (
        base["CFO"] > 0
    )

    base["ROE_POSITIVO"] = (
        base["ROE"] > 0
    )

    base["EBIT_POSITIVO"] = np.where(
        base["EH_FINANCEIRO"],
        np.nan,
        base["EBIT"] > 0,
    )

    # ========================================================
    # SANIDADE
    # ========================================================

    numeric = base.select_dtypes(
        include=np.number
    )

    if (
        np.isinf(numeric)
        .sum()
        .sum()
        != 0
    ):

        raise RuntimeError(
            "Indicadores contêm infinito."
        )

    return base


# ============================================================
# 4. RESUMO HISTÓRICO POR EMPRESA
# ============================================================

def build_company_summary(
    raw_indicators: pd.DataFrame,
) -> pd.DataFrame:

    base = raw_indicators.copy()

    resultados = []

    for cd_cvm, g in base.groupby("CD_CVM"):

        g = g.sort_values("ANO")

        nome = (
            g["DENOM_CIA_ATUAL"]
            .iloc[0]
        )

        motor = (
            g["MOTOR_FINAL"]
            .iloc[0]
        )

        elegivel = bool(
            g[
                "ELEGIVEL_DADOS_QUALITY"
            ]
            .fillna(False)
            .iloc[0]
        )

        validos_lucro = g[
            g[
                "LUCRO_LIQUIDO"
            ].notna()
        ]

        validos_cfo = g[
            g["CFO"].notna()
        ]

        validos_roe = g[
            g["ROE"].notna()
        ]

        # ====================================================
        # CAGR
        #
        # Primeiro e último ponto positivo válido.
        # Intervalo mínimo = 4 anos.
        # ====================================================

        receita_valida = g[
            g["RECEITA"].notna()
            &
            (
                g["RECEITA"] > 0
            )
        ]

        lucro_valido = g[
            g[
                "LUCRO_LIQUIDO"
            ].notna()
            &
            (
                g[
                    "LUCRO_LIQUIDO"
                ] > 0
            )
        ]

        cagr_receita = np.nan
        cagr_lucro = np.nan

        if len(receita_valida) >= 2:

            primeira = (
                receita_valida.iloc[0]
            )

            ultima = (
                receita_valida.iloc[-1]
            )

            intervalo = (
                ultima["ANO"]
                -
                primeira["ANO"]
            )

            if intervalo >= 4:

                cagr_receita = (
                    cagr_seguro(
                        primeira["RECEITA"],
                        ultima["RECEITA"],
                        intervalo,
                    )
                )

        if len(lucro_valido) >= 2:

            primeira = (
                lucro_valido.iloc[0]
            )

            ultima = (
                lucro_valido.iloc[-1]
            )

            intervalo = (
                ultima["ANO"]
                -
                primeira["ANO"]
            )

            if intervalo >= 4:

                cagr_lucro = (
                    cagr_seguro(
                        primeira[
                            "LUCRO_LIQUIDO"
                        ],
                        ultima[
                            "LUCRO_LIQUIDO"
                        ],
                        intervalo,
                    )
                )

        # ====================================================
        # TENDÊNCIA DA DÍVIDA LÍQUIDA
        #
        # Apenas não financeiros e >= 5 observações.
        # ====================================================

        dl = g[
            g[
                "DIVIDA_LIQUIDA"
            ].notna()
        ]

        tendencia_divida = np.nan

        if (
            motor not in FINANCEIROS
            and len(dl) >= 5
        ):

            primeira_dl = (
                dl.iloc[0][
                    "DIVIDA_LIQUIDA"
                ]
            )

            ultima_dl = (
                dl.iloc[-1][
                    "DIVIDA_LIQUIDA"
                ]
            )

            tendencia_divida = (
                ultima_dl
                -
                primeira_dl
            )

        # ====================================================
        # RESUMO
        # ====================================================

        resultados.append(
            {
                "CD_CVM":
                    cd_cvm,

                "DENOM_CIA_ATUAL":
                    nome,

                "MOTOR_FINAL":
                    motor,

                "ELEGIVEL_DADOS_QUALITY":
                    elegivel,

                # --------------------------------------------
                # Persistência
                # --------------------------------------------

                "ANOS_COM_LUCRO":
                    len(validos_lucro),

                "ANOS_LUCRO_POSITIVO":
                    int(
                        validos_lucro[
                            "LUCRO_POSITIVO"
                        ].sum()
                    ),

                "PCT_LUCRO_POSITIVO":
                    (
                        validos_lucro[
                            "LUCRO_POSITIVO"
                        ].mean()
                        if len(
                            validos_lucro
                        )
                        else np.nan
                    ),

                "ANOS_COM_CFO":
                    len(validos_cfo),

                "ANOS_CFO_POSITIVO":
                    int(
                        validos_cfo[
                            "CFO_POSITIVO"
                        ].sum()
                    ),

                "PCT_CFO_POSITIVO":
                    (
                        validos_cfo[
                            "CFO_POSITIVO"
                        ].mean()
                        if len(
                            validos_cfo
                        )
                        else np.nan
                    ),

                # --------------------------------------------
                # Rentabilidade
                # --------------------------------------------

                "ROE_MEDIANA":
                    validos_roe[
                        "ROE"
                    ].median(),

                "ROE_MEDIA":
                    validos_roe[
                        "ROE"
                    ].mean(),

                "PCT_ROE_POSITIVO":
                    (
                        validos_roe[
                            "ROE_POSITIVO"
                        ].mean()
                        if len(
                            validos_roe
                        )
                        else np.nan
                    ),

                # --------------------------------------------
                # ROIC
                # --------------------------------------------

                "ROIC_BRUTO_MEDIANA":
                    (
                        g[
                            "ROIC_BRUTO"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                # --------------------------------------------
                # Margens
                # --------------------------------------------

                "MARGEM_EBIT_MEDIANA":
                    (
                        g[
                            "MARGEM_EBIT"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                "MARGEM_EBIT_DESVIO":
                    (
                        g[
                            "MARGEM_EBIT"
                        ].std()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                "MARGEM_LIQUIDA_MEDIANA":
                    (
                        g[
                            "MARGEM_LIQUIDA"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                "MARGEM_LIQUIDA_DESVIO":
                    (
                        g[
                            "MARGEM_LIQUIDA"
                        ].std()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                # --------------------------------------------
                # Caixa
                # --------------------------------------------

                "CFO_LUCRO_MEDIANA":
                    g[
                        "CFO_LUCRO"
                    ].median(),

                "CFO_RECEITA_MEDIANA":
                    (
                        g[
                            "CFO_RECEITA"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                # --------------------------------------------
                # Dívida
                # --------------------------------------------

                "DIVIDA_BRUTA_PL_MEDIANA":
                    (
                        g[
                            "DIVIDA_BRUTA_PL"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                "DIVIDA_LIQUIDA_EBIT_MEDIANA":
                    (
                        g[
                            "DIVIDA_LIQUIDA_EBIT"
                        ].median()
                        if motor
                        not in FINANCEIROS
                        else np.nan
                    ),

                "VARIACAO_DIVIDA_LIQUIDA":
                    tendencia_divida,

                # --------------------------------------------
                # Crescimento
                # --------------------------------------------

                "CAGR_RECEITA":
                    cagr_receita,

                "CAGR_LUCRO":
                    cagr_lucro,

                "CRESC_RECEITA_YOY_MEDIANA":
                    g[
                        "CRESC_RECEITA_YOY"
                    ].median(),

                "CRESC_LUCRO_YOY_MEDIANA":
                    g[
                        "CRESC_LUCRO_YOY"
                    ].median(),
            }
        )

    empresa = pd.DataFrame(
        resultados
    )

    if empresa[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado no resumo "
            "histórico da Cell17."
        )

    return empresa


# ============================================================
# 5. ENGINE COMPLETO
# ============================================================

def run_fundamental_indicators(
    fundamental_base: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    raw = build_raw_indicators(
        fundamental_base
    )

    company = build_company_summary(
        raw
    )

    return raw, company


# ============================================================
# 6. SELF TEST
# ============================================================

def _self_test():

    assert (
        FINANCEIROS
        ==
        {
            "FINANCEIRO_BANCO",
            "FINANCEIRO_SEGUROS",
            "FINANCEIRO_ESPECIAL",
        }
    )

    assert (
        cagr_seguro(
            100,
            121,
            2,
        )
        == 0.1
    )

    assert np.isnan(
        cagr_seguro(
            -100,
            121,
            2,
        )
    )

    print(
        "fundamental_indicators_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
