"""
B3 INVESTMENT ENGINE
CURRENT FUNDAMENTAL CONTEXT V1

OBJETIVO
--------
Criar uma camada fundamental corrente usando ITR,
SEM alterar a metodologia histórica validada.

PRINCÍPIO CENTRAL
-----------------
QUALITY SCORE:
    continua baseado exclusivamente na série anual DFP.

ITR:
    fornece somente CONTEXTO FUNDAMENTAL CORRENTE.

Portanto este módulo:
    - NÃO recalcula Quality Score;
    - NÃO substitui exercício anual por trimestre;
    - NÃO altera Quality Gate;
    - NÃO altera Valuation Score;
    - NÃO altera ranking;
    - NÃO recupera empresa reprovada;
    - NÃO cria novo score.

TRATAMENTO DO ITR
-----------------
BPA/BPP:
    fotografia contábil mais recente da companhia.

DRE/DFC:
    seleciona, para a data de referência mais recente,
    o período acumulado mais longo disponível.

Isso evita escolher acidentalmente apenas o trimestre
isolado quando existe YTD/acumulado para a mesma data.

O início do exercício NÃO é fixado em 01/01.
A seleção é feita pelos próprios períodos publicados
pela companhia.
"""

from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd


# ============================================================
# 1. CONSTANTES
# ============================================================

FINANCIAL_ENGINES = {
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
}


# ============================================================
# 2. NORMALIZAÇÃO
# ============================================================

def normalize_text(value) -> str:

    if pd.isna(value):
        return ""

    value = str(value).upper().strip()

    value = "".join(
        c
        for c in unicodedata.normalize(
            "NFKD",
            value,
        )
        if not unicodedata.combining(c)
    )

    return " ".join(
        value.split()
    )


# ============================================================
# 3. PREPARAÇÃO ITR
# ============================================================

def prepare_itr_statement(
    df: pd.DataFrame,
    statement: str,
) -> pd.DataFrame:

    if df is None or df.empty:
        return pd.DataFrame()

    required = {
        "CD_CVM",
        "DT_REFER",
        "VERSAO",
        "ORDEM_EXERC",
        "CD_CONTA",
        "DS_CONTA",
        "VL_CONTA",
    }

    missing = required - set(df.columns)

    if missing:

        raise ValueError(
            f"{statement}: colunas ausentes: "
            + ", ".join(sorted(missing))
        )

    x = df.copy()

    x["CD_CVM"] = pd.to_numeric(
        x["CD_CVM"],
        errors="coerce",
    )

    x["VERSAO"] = pd.to_numeric(
        x["VERSAO"],
        errors="coerce",
    )

    x["VL_CONTA"] = pd.to_numeric(
        x["VL_CONTA"],
        errors="coerce",
    )

    x["DT_REFER"] = pd.to_datetime(
        x["DT_REFER"],
        errors="coerce",
    )

    if "DT_INI_EXERC" in x.columns:

        x["DT_INI_EXERC"] = (
            pd.to_datetime(
                x["DT_INI_EXERC"],
                errors="coerce",
            )
        )

    if "DT_FIM_EXERC" in x.columns:

        x["DT_FIM_EXERC"] = (
            pd.to_datetime(
                x["DT_FIM_EXERC"],
                errors="coerce",
            )
        )

    x["ORDEM_NORM"] = (
        x["ORDEM_EXERC"]
        .map(normalize_text)
    )

    x["DS_NORM"] = (
        x["DS_CONTA"]
        .map(normalize_text)
    )

    # Mesma proteção já utilizada
    # na base fundamental anual.

    x = x[
        x["ORDEM_NORM"].eq(
            "ULTIMO"
        )
    ].copy()

    x = x.dropna(
        subset=[
            "CD_CVM",
            "DT_REFER",
        ]
    )

    return x


# ============================================================
# 4. ÚLTIMA DATA DISPONÍVEL POR EMPRESA
# ============================================================

def keep_latest_reference_date(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if df.empty:
        return df.copy()

    latest = (
        df.groupby(
            "CD_CVM"
        )["DT_REFER"]
        .transform("max")
    )

    return df[
        df["DT_REFER"].eq(
            latest
        )
    ].copy()


# ============================================================
# 5. ÚLTIMA VERSÃO
# ============================================================

def keep_latest_version(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if df.empty:
        return df.copy()

    max_version = (
        df.groupby(
            [
                "CD_CVM",
                "DT_REFER",
            ]
        )["VERSAO"]
        .transform("max")
    )

    return df[
        df["VERSAO"].eq(
            max_version
        )
        |
        (
            df["VERSAO"].isna()
            &
            max_version.isna()
        )
    ].copy()


# ============================================================
# 6. BPA/BPP — FOTOGRAFIA MAIS RECENTE
# ============================================================

def select_latest_stock_statement(
    df: pd.DataFrame,
    statement: str,
) -> pd.DataFrame:

    x = prepare_itr_statement(
        df,
        statement,
    )

    x = keep_latest_reference_date(
        x
    )

    x = keep_latest_version(
        x
    )

    return x


# ============================================================
# 7. DRE/DFC — ACUMULADO MAIS LONGO
# ============================================================

def select_latest_cumulative_statement(
    df: pd.DataFrame,
    statement: str,
) -> pd.DataFrame:

    x = prepare_itr_statement(
        df,
        statement,
    )

    required = {
        "DT_INI_EXERC",
        "DT_FIM_EXERC",
    }

    missing = required - set(x.columns)

    if missing:

        raise ValueError(
            f"{statement}: faltam campos "
            "de período: "
            + ", ".join(sorted(missing))
        )

    # --------------------------------------------------------
    # Primeiro:
    # última data de referência da companhia.
    # --------------------------------------------------------

    x = keep_latest_reference_date(
        x
    )

    # --------------------------------------------------------
    # Depois:
    # última versão.
    # --------------------------------------------------------

    x = keep_latest_version(
        x
    )

    # --------------------------------------------------------
    # Período válido.
    # --------------------------------------------------------

    x = x[
        x["DT_INI_EXERC"].notna()
        &
        x["DT_FIM_EXERC"].notna()
    ].copy()

    x["PERIODO_DIAS"] = (
        x["DT_FIM_EXERC"]
        -
        x["DT_INI_EXERC"]
    ).dt.days + 1

    x = x[
        x["PERIODO_DIAS"] > 0
    ].copy()

    # --------------------------------------------------------
    # REGRA CRÍTICA:
    #
    # para a última data da empresa,
    # selecionar o período de maior duração.
    #
    # Exemplo:
    # 30/09:
    #   01/01 → 30/09 = acumulado
    #   01/04 → 30/09 = semestre
    #   01/07 → 30/09 = trimestre
    #
    # selecionamos o primeiro.
    #
    # Não presumimos que o exercício
    # obrigatoriamente começa em 01/01.
    # --------------------------------------------------------

    max_period = (
        x.groupby(
            [
                "CD_CVM",
                "DT_REFER",
            ]
        )["PERIODO_DIAS"]
        .transform("max")
    )

    x = x[
        x["PERIODO_DIAS"].eq(
            max_period
        )
    ].copy()

    return x


# ============================================================
# 8. EXTRAÇÃO POR CÓDIGO
# ============================================================

def extract_code(
    df: pd.DataFrame,
    code: str,
    output_name: str,
) -> pd.DataFrame:

    if df.empty:

        return pd.DataFrame(
            columns=[
                "CD_CVM",
                output_name,
            ]
        )

    x = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(code)
    ].copy()

    if x.empty:

        return pd.DataFrame(
            columns=[
                "CD_CVM",
                output_name,
            ]
        )

    x = (
        x.sort_values(
            [
                "CD_CVM",
                "DT_REFER",
                "VERSAO",
            ]
        )
        .drop_duplicates(
            "CD_CVM",
            keep="last",
        )
    )

    return (
        x[
            [
                "CD_CVM",
                "VL_CONTA",
            ]
        ]
        .rename(
            columns={
                "VL_CONTA":
                    output_name
            }
        )
    )


# ============================================================
# 9. EXTRAÇÃO POR DESCRIÇÃO
# ============================================================

def extract_description(
    df: pd.DataFrame,
    descriptions: set[str],
    output_name: str,
) -> pd.DataFrame:

    if df.empty:

        return pd.DataFrame(
            columns=[
                "CD_CVM",
                output_name,
            ]
        )

    normalized = {
        normalize_text(x)
        for x in descriptions
    }

    x = df[
        df["DS_NORM"].isin(
            normalized
        )
    ].copy()

    if x.empty:

        return pd.DataFrame(
            columns=[
                "CD_CVM",
                output_name,
            ]
        )

    x = (
        x.sort_values(
            [
                "CD_CVM",
                "DT_REFER",
                "VERSAO",
                "CD_CONTA",
            ]
        )
        .drop_duplicates(
            "CD_CVM",
            keep="last",
        )
    )

    return (
        x[
            [
                "CD_CVM",
                "VL_CONTA",
            ]
        ]
        .rename(
            columns={
                "VL_CONTA":
                    output_name
            }
        )
    )


# ============================================================
# 10. METADADOS DO PERÍODO
# ============================================================

def build_period_metadata(
    dre: pd.DataFrame,
) -> pd.DataFrame:

    if dre.empty:

        return pd.DataFrame(
            columns=[
                "CD_CVM",
                "CURRENT_DT_REFER",
                "CURRENT_DT_INI_EXERC",
                "CURRENT_DT_FIM_EXERC",
                "CURRENT_PERIODO_DIAS",
            ]
        )

    x = (
        dre[
            [
                "CD_CVM",
                "DT_REFER",
                "DT_INI_EXERC",
                "DT_FIM_EXERC",
                "PERIODO_DIAS",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "CD_CVM",
                "DT_REFER",
                "PERIODO_DIAS",
            ]
        )
        .drop_duplicates(
            "CD_CVM",
            keep="last",
        )
    )

    return x.rename(
        columns={
            "DT_REFER":
                "CURRENT_DT_REFER",

            "DT_INI_EXERC":
                "CURRENT_DT_INI_EXERC",

            "DT_FIM_EXERC":
                "CURRENT_DT_FIM_EXERC",

            "PERIODO_DIAS":
                "CURRENT_PERIODO_DIAS",
        }
    )


# ============================================================
# 11. CONTEXTO FUNDAMENTAL CORRENTE
# ============================================================

def build_current_fundamental_context(
    architecture: pd.DataFrame,
    itr_statements: dict[
        str,
        pd.DataFrame,
    ],
) -> pd.DataFrame:

    required_architecture = {
        "CD_CVM",
        "DENOM_CIA_ATUAL",
        "MOTOR_FINAL",
    }

    missing = (
        required_architecture
        -
        set(architecture.columns)
    )

    if missing:

        raise ValueError(
            "Arquitetura sem colunas: "
            + ", ".join(
                sorted(missing)
            )
        )

    required_statements = {
        "BPA",
        "BPP",
        "DRE",
        "DFC_MI",
        "DFC_MD",
    }

    missing_statements = (
        required_statements
        -
        set(itr_statements)
    )

    if missing_statements:

        raise ValueError(
            "ITR sem demonstrativos: "
            + ", ".join(
                sorted(
                    missing_statements
                )
            )
        )

    companies = (
        architecture[
            [
                "CD_CVM",
                "DENOM_CIA_ATUAL",
                "MOTOR_FINAL",
            ]
        ]
        .copy()
        .drop_duplicates(
            "CD_CVM"
        )
    )

    companies["CD_CVM"] = (
        pd.to_numeric(
            companies["CD_CVM"],
            errors="coerce",
        )
    )

    companies = companies.dropna(
        subset=["CD_CVM"]
    )

    # ========================================================
    # SELEÇÃO TEMPORAL
    # ========================================================

    bpa = select_latest_stock_statement(
        itr_statements["BPA"],
        "BPA",
    )

    bpp = select_latest_stock_statement(
        itr_statements["BPP"],
        "BPP",
    )

    dre = (
        select_latest_cumulative_statement(
            itr_statements["DRE"],
            "DRE",
        )
    )

    dfc_mi = (
        select_latest_cumulative_statement(
            itr_statements["DFC_MI"],
            "DFC_MI",
        )
        if not itr_statements[
            "DFC_MI"
        ].empty
        else pd.DataFrame()
    )

    dfc_md = (
        select_latest_cumulative_statement(
            itr_statements["DFC_MD"],
            "DFC_MD",
        )
        if not itr_statements[
            "DFC_MD"
        ].empty
        else pd.DataFrame()
    )

    # ========================================================
    # CONTAS — MESMA SEMÂNTICA DA BASE ANUAL
    # ========================================================

    ativo = extract_code(
        bpa,
        "1",
        "CURRENT_ATIVO_TOTAL",
    )

    caixa = extract_code(
        bpa,
        "1.01.01",
        "CURRENT_CAIXA",
    )

    divida_cp = extract_code(
        bpp,
        "2.01.04",
        "CURRENT_DIVIDA_CP",
    )

    divida_lp = extract_code(
        bpp,
        "2.02.01",
        "CURRENT_DIVIDA_LP",
    )

    receita = extract_code(
        dre,
        "3.01",
        "CURRENT_RECEITA_ACUM",
    )

    ebit = extract_code(
        dre,
        "3.05",
        "CURRENT_EBIT_ACUM",
    )

    pl = extract_description(
        bpp,
        {
            "Patrimônio Líquido Consolidado",
        },
        "CURRENT_PATRIMONIO_LIQUIDO",
    )

    lucro = extract_description(
        dre,
        {
            "Lucro/Prejuízo Consolidado do Período",
            "Lucro ou Prejuízo Líquido Consolidado do Período",
        },
        "CURRENT_LUCRO_ACUM",
    )

    # ========================================================
    # CFO — MI PRIMEIRO, MD FALLBACK
    # ========================================================

    cfo_mi = extract_code(
        dfc_mi,
        "6.01",
        "CURRENT_CFO_MI",
    )

    cfo_md = extract_code(
        dfc_md,
        "6.01",
        "CURRENT_CFO_MD",
    )

    cfo = cfo_mi.merge(
        cfo_md,
        on="CD_CVM",
        how="outer",
    )

    cfo["CURRENT_CFO_ACUM"] = (
        cfo["CURRENT_CFO_MI"]
        .combine_first(
            cfo["CURRENT_CFO_MD"]
        )
    )

    cfo[
        "CURRENT_METODO_CFO"
    ] = np.select(
        [
            cfo[
                "CURRENT_CFO_MI"
            ].notna(),

            cfo[
                "CURRENT_CFO_MD"
            ].notna(),
        ],
        [
            "MI",
            "MD",
        ],
        default="",
    )

    cfo = cfo[
        [
            "CD_CVM",
            "CURRENT_CFO_ACUM",
            "CURRENT_METODO_CFO",
        ]
    ]

    # ========================================================
    # METADADOS
    # ========================================================

    metadata = build_period_metadata(
        dre
    )

    # ========================================================
    # MERGE
    # ========================================================

    result = companies.copy()

    for table in [
        metadata,
        ativo,
        pl,
        caixa,
        divida_cp,
        divida_lp,
        receita,
        ebit,
        lucro,
        cfo,
    ]:

        result = result.merge(
            table,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )

    # ========================================================
    # DÍVIDA
    # ========================================================

    result[
        "CURRENT_DIVIDA_BRUTA"
    ] = (
        result[
            [
                "CURRENT_DIVIDA_CP",
                "CURRENT_DIVIDA_LP",
            ]
        ]
        .sum(
            axis=1,
            min_count=1,
        )
    )

    result[
        "CURRENT_DIVIDA_LIQUIDA"
    ] = (
        result[
            "CURRENT_DIVIDA_BRUTA"
        ]
        -
        result[
            "CURRENT_CAIXA"
        ]
    )

    # ========================================================
    # COBERTURA DO CONTEXTO
    # ========================================================

    result[
        "CURRENT_CONTEXT_AVAILABLE"
    ] = (
        result[
            "CURRENT_DT_REFER"
        ].notna()
    )

    result[
        "CURRENT_IS_FINANCIAL"
    ] = (
        result["MOTOR_FINAL"]
        .isin(
            FINANCIAL_ENGINES
        )
    )

    # ========================================================
    # QUALIDADE DOS DADOS CORRENTES
    #
    # Isto NÃO é Quality Score.
    # É somente auditoria de disponibilidade.
    # ========================================================

    result[
        "CURRENT_BALANCE_AVAILABLE"
    ] = (
        result[
            "CURRENT_ATIVO_TOTAL"
        ].notna()
        |
        result[
            "CURRENT_PATRIMONIO_LIQUIDO"
        ].notna()
    )

    result[
        "CURRENT_RESULT_AVAILABLE"
    ] = (
        result[
            "CURRENT_LUCRO_ACUM"
        ].notna()
    )

    result[
        "CURRENT_DATA_STATUS"
    ] = np.select(
        [
            ~result[
                "CURRENT_CONTEXT_AVAILABLE"
            ],

            (
                result[
                    "CURRENT_CONTEXT_AVAILABLE"
                ]
                &
                ~result[
                    "CURRENT_RESULT_AVAILABLE"
                ]
            ),

            (
                result[
                    "CURRENT_CONTEXT_AVAILABLE"
                ]
                &
                result[
                    "CURRENT_RESULT_AVAILABLE"
                ]
                &
                ~result[
                    "CURRENT_BALANCE_AVAILABLE"
                ]
            ),
        ],
        [
            "DATA_INSUFFICIENT",
            "RESULT_INSUFFICIENT",
            "BALANCE_INSUFFICIENT",
        ],
        default="OK",
    )

    # ========================================================
    # PROTEÇÕES METODOLÓGICAS EXPLÍCITAS
    # ========================================================

    result[
        "ALTERA_QUALITY_SCORE"
    ] = False

    result[
        "ALTERA_QUALITY_GATE"
    ] = False

    result[
        "ALTERA_VALUATION_SCORE"
    ] = False

    result[
        "ALTERA_RANKING"
    ] = False

    result[
        "RESGATA_REPROVADA"
    ] = False

    result[
        "CURRENT_CONTEXT_ROLE"
    ] = (
        "INFORMATIONAL_CURRENT_CONTEXT"
    )

    # ========================================================
    # INTEGRIDADE
    # ========================================================

    if result[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado no contexto "
            "fundamental corrente."
        )

    if (
        result[
            "ALTERA_QUALITY_SCORE"
        ].any()
        or
        result[
            "ALTERA_QUALITY_GATE"
        ].any()
        or
        result[
            "ALTERA_VALUATION_SCORE"
        ].any()
        or
        result[
            "ALTERA_RANKING"
        ].any()
        or
        result[
            "RESGATA_REPROVADA"
        ].any()
    ):

        raise RuntimeError(
            "Violação da política de "
            "preservação metodológica."
        )

    return (
        result.sort_values(
            "CD_CVM"
        )
        .reset_index(drop=True)
    )


# ============================================================
# 12. AUDITORIA DE PERÍODOS SELECIONADOS
# ============================================================

def audit_selected_periods(
    result: pd.DataFrame,
) -> pd.DataFrame:

    columns = [
        "CD_CVM",
        "DENOM_CIA_ATUAL",
        "MOTOR_FINAL",
        "CURRENT_DT_REFER",
        "CURRENT_DT_INI_EXERC",
        "CURRENT_DT_FIM_EXERC",
        "CURRENT_PERIODO_DIAS",
        "CURRENT_CONTEXT_AVAILABLE",
        "CURRENT_DATA_STATUS",
    ]

    existing = [
        c
        for c in columns
        if c in result.columns
    ]

    return (
        result[existing]
        .copy()
        .sort_values(
            [
                "CURRENT_DT_REFER",
                "CD_CVM",
            ],
            ascending=[
                False,
                True,
            ],
            na_position="last",
        )
        .reset_index(drop=True)
    )


# ============================================================
# 13. SELF TEST
# ============================================================

def _self_test():

    # --------------------------------------------------------
    # Teste crítico:
    #
    # mesma companhia,
    # mesma referência,
    # 9M e 3M.
    #
    # deve selecionar 9M.
    # --------------------------------------------------------

    test = pd.DataFrame(
        {
            "CD_CVM": [
                1,
                1,
            ],

            "DT_REFER": [
                "2025-09-30",
                "2025-09-30",
            ],

            "VERSAO": [
                1,
                1,
            ],

            "ORDEM_EXERC": [
                "ÚLTIMO",
                "ÚLTIMO",
            ],

            "DT_INI_EXERC": [
                "2025-01-01",
                "2025-07-01",
            ],

            "DT_FIM_EXERC": [
                "2025-09-30",
                "2025-09-30",
            ],

            "CD_CONTA": [
                "3.01",
                "3.01",
            ],

            "DS_CONTA": [
                "Receita",
                "Receita",
            ],

            "VL_CONTA": [
                900,
                300,
            ],
        }
    )

    selected = (
        select_latest_cumulative_statement(
            test,
            "DRE",
        )
    )

    assert len(selected) == 1

    assert (
        selected.iloc[0][
            "VL_CONTA"
        ]
        ==
        900
    )

    assert (
        selected.iloc[0][
            "DT_INI_EXERC"
        ]
        ==
        pd.Timestamp(
            "2025-01-01"
        )
    )

    # --------------------------------------------------------
    # Exercício não iniciado em janeiro.
    # Deve preservar o período publicado.
    # --------------------------------------------------------

    non_calendar = pd.DataFrame(
        {
            "CD_CVM": [
                2,
                2,
            ],

            "DT_REFER": [
                "2025-03-31",
                "2025-03-31",
            ],

            "VERSAO": [
                1,
                1,
            ],

            "ORDEM_EXERC": [
                "ÚLTIMO",
                "ÚLTIMO",
            ],

            "DT_INI_EXERC": [
                "2024-07-01",
                "2025-01-01",
            ],

            "DT_FIM_EXERC": [
                "2025-03-31",
                "2025-03-31",
            ],

            "CD_CONTA": [
                "3.01",
                "3.01",
            ],

            "DS_CONTA": [
                "Receita",
                "Receita",
            ],

            "VL_CONTA": [
                900,
                300,
            ],
        }
    )

    selected = (
        select_latest_cumulative_statement(
            non_calendar,
            "DRE",
        )
    )

    assert len(selected) == 1

    assert (
        selected.iloc[0][
            "DT_INI_EXERC"
        ]
        ==
        pd.Timestamp(
            "2024-07-01"
        )
    )

    print(
        "current_fundamental_context_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
