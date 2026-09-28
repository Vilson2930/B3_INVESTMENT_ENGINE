"""
B3 INVESTMENT ENGINE
CVM FUNDAMENTAL BASE V1

Reprodução modular da Célula 16 do estudo original.

OBJETIVO
--------
Transformar demonstrações financeiras CVM em uma base
empresa-ano que alimenta o Fundamental Indicators V1.

METODOLOGIA PRESERVADA
----------------------
- ORDEM_EXERC = ÚLTIMO, por igualdade exata.
- última VERSAO disponível.
- ATIVO TOTAL: BPA conta 1
- CAIXA: BPA conta 1.01.01
- DÍVIDA CP: BPP conta 2.01.04
- DÍVIDA LP: BPP conta 2.02.01
- RECEITA: DRE conta 3.01
- EBIT: DRE conta 3.05
- PL: descrição econômica consolidada
- LUCRO: descrição econômica consolidada
- CFO: DFC_MI conta 6.01; DFC_MD como fallback
- dívida bruta = CP + LP
- dívida líquida = dívida bruta - caixa

SUFICIÊNCIA PARA QUALITY
------------------------
Financeiros:
    >= 5 anos de PL + lucro

Não financeiros:
    >= 5 anos de PL + lucro + receita

NÃO CALCULA
-----------
- Quality Score
- Valuation
- Investibilidade B3
- Ranking
- Análise técnica
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd


FINANCIAL_ENGINES = {
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
}


# ============================================================
# 1. NORMALIZAÇÃO — CELL16
# ============================================================

def normalize_text(value):

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

    return re.sub(
        r"\s+",
        " ",
        value,
    )


# ============================================================
# 2. PADRONIZAÇÃO DAS DEMONSTRAÇÕES
# ============================================================

def prepare_statement(
    df: pd.DataFrame,
) -> pd.DataFrame:

    required = {
        "CD_CVM",
        "ANO",
        "CD_CONTA",
        "DS_CONTA",
        "VL_CONTA",
        "ORDEM_EXERC",
    }

    missing = required - set(df.columns)

    if missing:

        raise ValueError(
            "Demonstração CVM sem colunas "
            "obrigatórias: "
            + ", ".join(sorted(missing))
        )

    x = df.copy()

    x["CD_CVM"] = pd.to_numeric(
        x["CD_CVM"],
        errors="coerce",
    )

    x["ANO"] = pd.to_numeric(
        x["ANO"],
        errors="coerce",
    )

    x["VL_CONTA"] = pd.to_numeric(
        x["VL_CONTA"],
        errors="coerce",
    )

    x["CD_CONTA"] = (
        x["CD_CONTA"]
        .astype(str)
        .str.strip()
    )

    x["DS_NORM"] = (
        x["DS_CONTA"]
        .map(normalize_text)
    )

    x["ORDEM_NORM"] = (
        x["ORDEM_EXERC"]
        .map(normalize_text)
    )

    # ========================================================
    # REGRA CRÍTICA DO ESTUDO:
    #
    # ÚLTIMO exato.
    #
    # NÃO usar contains("ULTIMO").
    # ========================================================

    x = x[
        x["ORDEM_NORM"].eq("ULTIMO")
    ].copy()

    # ========================================================
    # ÚLTIMA VERSÃO DA DEMONSTRAÇÃO
    # ========================================================

    if "VERSAO" in x.columns:

        x["VERSAO_NUM"] = pd.to_numeric(
            x["VERSAO"],
            errors="coerce",
        )

        max_version = (
            x.groupby(
                [
                    "CD_CVM",
                    "ANO",
                ]
            )["VERSAO_NUM"]
            .transform("max")
        )

        x = x[
            x["VERSAO_NUM"].eq(
                max_version
            )
            |
            (
                x["VERSAO_NUM"].isna()
                &
                max_version.isna()
            )
        ].copy()

    return x


# ============================================================
# 3. EXTRATOR POR CÓDIGO — CELL16
# ============================================================

def extract_by_code(
    df: pd.DataFrame,
    code: str,
    output_name: str,
) -> pd.DataFrame:

    x = df[
        df["CD_CONTA"]
        .astype(str)
        .str.strip()
        .eq(code)
    ].copy()

    x = (
        x.sort_values(
            [
                "CD_CVM",
                "ANO",
            ]
        )
        .drop_duplicates(
            [
                "CD_CVM",
                "ANO",
            ],
            keep="last",
        )
    )

    return (
        x[
            [
                "CD_CVM",
                "ANO",
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
# 4. EXTRATOR POR DESCRIÇÃO ECONÔMICA
# ============================================================

def extract_by_description(
    df: pd.DataFrame,
    descriptions: set[str],
    output_name: str,
) -> pd.DataFrame:

    normalized = {
        normalize_text(d)
        for d in descriptions
    }

    x = df[
        df["DS_NORM"].isin(
            normalized
        )
    ].copy()

    # Duplicação literal pode ser removida.

    x = x.drop_duplicates(
        [
            "CD_CVM",
            "ANO",
            "CD_CONTA",
            "VL_CONTA",
        ]
    )

    # Cell16:
    # não somar contas.
    # selecionar a conta consolidada pela descrição.

    x = (
        x.sort_values(
            [
                "CD_CVM",
                "ANO",
                "CD_CONTA",
            ]
        )
        .drop_duplicates(
            [
                "CD_CVM",
                "ANO",
            ],
            keep="last",
        )
    )

    return (
        x[
            [
                "CD_CVM",
                "ANO",
                "VL_CONTA",
                "CD_CONTA",
            ]
        ]
        .rename(
            columns={
                "VL_CONTA":
                    output_name,

                "CD_CONTA":
                    f"COD_{output_name}",
            }
        )
    )


# ============================================================
# 5. VALIDAÇÃO DA ARQUITETURA
# ============================================================

def validate_architecture(
    architecture: pd.DataFrame,
) -> pd.DataFrame:

    required = {
        "CD_CVM",
        "DENOM_CIA_ATUAL",
        "MOTOR_FINAL",
    }

    missing = (
        required
        - set(architecture.columns)
    )

    if missing:

        raise ValueError(
            "Arquitetura setorial sem colunas "
            "obrigatórias: "
            + ", ".join(sorted(missing))
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
    )

    companies["CD_CVM"] = pd.to_numeric(
        companies["CD_CVM"],
        errors="coerce",
    )

    companies = (
        companies
        .dropna(
            subset=["CD_CVM"]
        )
        .drop_duplicates(
            "CD_CVM"
        )
        .reset_index(drop=True)
    )

    if companies.empty:

        raise ValueError(
            "Arquitetura setorial vazia."
        )

    return companies


# ============================================================
# 6. ANOS DISPONÍVEIS
# ============================================================

def discover_years(
    statements: dict[str, pd.DataFrame],
) -> list[int]:

    years = set()

    for df in statements.values():

        if "ANO" not in df.columns:
            continue

        values = pd.to_numeric(
            df["ANO"],
            errors="coerce",
        ).dropna()

        years.update(
            values.astype(int).tolist()
        )

    years = sorted(years)

    if not years:

        raise ValueError(
            "Nenhum ano CVM encontrado."
        )

    return years


# ============================================================
# 7. ENGINE — BASE FUNDAMENTAL
# ============================================================

def build_cvm_fundamental_base(
    architecture: pd.DataFrame,
    statements: dict[str, pd.DataFrame],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:

    required_statements = {
        "BPA",
        "BPP",
        "DRE",
        "DFC_MI",
        "DFC_MD",
    }

    missing = (
        required_statements
        - set(statements.keys())
    )

    if missing:

        raise ValueError(
            "Demonstrações ausentes: "
            + ", ".join(sorted(missing))
        )

    companies = validate_architecture(
        architecture
    )

    # ========================================================
    # PREPARAR CVM
    # ========================================================

    BPA = prepare_statement(
        statements["BPA"]
    )

    BPP = prepare_statement(
        statements["BPP"]
    )

    DRE = prepare_statement(
        statements["DRE"]
    )

    DFC_MI = prepare_statement(
        statements["DFC_MI"]
    )

    DFC_MD = prepare_statement(
        statements["DFC_MD"]
    )

    prepared = {
        "BPA": BPA,
        "BPP": BPP,
        "DRE": DRE,
        "DFC_MI": DFC_MI,
        "DFC_MD": DFC_MD,
    }

    years = discover_years(
        prepared
    )

    # ========================================================
    # CONTAS EXATAS — CELL16
    # ========================================================

    ativo = extract_by_code(
        BPA,
        "1",
        "ATIVO_TOTAL",
    )

    caixa = extract_by_code(
        BPA,
        "1.01.01",
        "CAIXA",
    )

    divida_cp = extract_by_code(
        BPP,
        "2.01.04",
        "DIVIDA_CP",
    )

    divida_lp = extract_by_code(
        BPP,
        "2.02.01",
        "DIVIDA_LP",
    )

    receita = extract_by_code(
        DRE,
        "3.01",
        "RECEITA",
    )

    ebit = extract_by_code(
        DRE,
        "3.05",
        "EBIT",
    )

    # ========================================================
    # PL CONSOLIDADO
    # ========================================================

    pl = extract_by_description(
        BPP,
        {
            "Patrimônio Líquido Consolidado",
        },
        "PATRIMONIO_LIQUIDO",
    )

    # ========================================================
    # LUCRO CONSOLIDADO
    # ========================================================

    lucro = extract_by_description(
        DRE,
        {
            "Lucro/Prejuízo Consolidado do Período",
            "Lucro ou Prejuízo Líquido Consolidado do Período",
        },
        "LUCRO_LIQUIDO",
    )

    # ========================================================
    # CFO
    #
    # MI primeiro.
    # MD somente como fallback.
    # ========================================================

    cfo_mi = extract_by_code(
        DFC_MI,
        "6.01",
        "CFO_MI",
    )

    cfo_md = extract_by_code(
        DFC_MD,
        "6.01",
        "CFO_MD",
    )

    cfo = cfo_mi.merge(
        cfo_md,
        on=[
            "CD_CVM",
            "ANO",
        ],
        how="outer",
    )

    cfo["CFO"] = (
        cfo["CFO_MI"]
        .combine_first(
            cfo["CFO_MD"]
        )
    )

    cfo["METODO_CFO"] = np.select(
        [
            cfo["CFO_MI"].notna(),
            cfo["CFO_MD"].notna(),
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
            "ANO",
            "CFO",
            "METODO_CFO",
        ]
    ]

    # ========================================================
    # GRADE EMPRESA × ANO
    #
    # No benchmark:
    # 568 × 7 = 3.976.
    #
    # Em produção:
    # anos são descobertos automaticamente.
    # ========================================================

    year_frame = pd.DataFrame(
        {
            "ANO": years,
        }
    )

    companies = companies.copy()
    year_frame = year_frame.copy()

    companies["_KEY"] = 1
    year_frame["_KEY"] = 1

    base = (
        companies
        .merge(
            year_frame,
            on="_KEY",
        )
        .drop(
            columns="_KEY"
        )
    )

    # ========================================================
    # MERGE CONTÁBIL
    # ========================================================

    for table in [
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

        base = base.merge(
            table,
            on=[
                "CD_CVM",
                "ANO",
            ],
            how="left",
            validate="one_to_one",
        )

    # ========================================================
    # DÍVIDA — CELL16
    # ========================================================

    base["DIVIDA_BRUTA"] = (
        base[
            [
                "DIVIDA_CP",
                "DIVIDA_LP",
            ]
        ]
        .sum(
            axis=1,
            min_count=1,
        )
    )

    base["DIVIDA_LIQUIDA"] = (
        base["DIVIDA_BRUTA"]
        -
        base["CAIXA"]
    )

    # ========================================================
    # APLICABILIDADE POR MOTOR
    # ========================================================

    base["MOTOR_FINANCEIRO"] = (
        base["MOTOR_FINAL"]
        .isin(
            FINANCIAL_ENGINES
        )
    )

    base[
        "APLICA_METRICAS_OPERACIONAIS"
    ] = (
        ~base["MOTOR_FINANCEIRO"]
    )

    # ========================================================
    # SUFICIÊNCIA CONTÁBIL
    # ========================================================

    base["TEM_ATIVO"] = (
        base["ATIVO_TOTAL"].notna()
        &
        (base["ATIVO_TOTAL"] > 0)
    )

    base["TEM_PL"] = (
        base[
            "PATRIMONIO_LIQUIDO"
        ].notna()
    )

    base["TEM_LUCRO"] = (
        base[
            "LUCRO_LIQUIDO"
        ].notna()
    )

    base["TEM_RECEITA"] = (
        base["RECEITA"].notna()
    )

    base["TEM_EBIT"] = (
        base["EBIT"].notna()
    )

    base["TEM_CFO"] = (
        base["CFO"].notna()
    )

    # ========================================================
    # COBERTURA HISTÓRICA
    # ========================================================

    coverage = (
        base.groupby(
            [
                "CD_CVM",
                "DENOM_CIA_ATUAL",
                "MOTOR_FINAL",
            ],
            as_index=False,
        )
        .agg(
            ANOS_ATIVO=(
                "TEM_ATIVO",
                "sum",
            ),
            ANOS_PL=(
                "TEM_PL",
                "sum",
            ),
            ANOS_LUCRO=(
                "TEM_LUCRO",
                "sum",
            ),
            ANOS_RECEITA=(
                "TEM_RECEITA",
                "sum",
            ),
            ANOS_EBIT=(
                "TEM_EBIT",
                "sum",
            ),
            ANOS_CFO=(
                "TEM_CFO",
                "sum",
            ),
        )
    )

    # ========================================================
    # REGRA EXATA DE ELEGIBILIDADE DA CELL16
    # ========================================================

    coverage[
        "ELEGIVEL_DADOS_QUALITY"
    ] = np.where(
        coverage[
            "MOTOR_FINAL"
        ].isin(
            FINANCIAL_ENGINES
        ),

        (
            (
                coverage[
                    "ANOS_PL"
                ] >= 5
            )
            &
            (
                coverage[
                    "ANOS_LUCRO"
                ] >= 5
            )
        ),

        (
            (
                coverage[
                    "ANOS_PL"
                ] >= 5
            )
            &
            (
                coverage[
                    "ANOS_LUCRO"
                ] >= 5
            )
            &
            (
                coverage[
                    "ANOS_RECEITA"
                ] >= 5
            )
        ),
    )

    base = base.merge(
        coverage[
            [
                "CD_CVM",
                "ELEGIVEL_DADOS_QUALITY",
            ]
        ],
        on="CD_CVM",
        how="left",
        validate="many_to_one",
    )

    # ========================================================
    # INTEGRIDADE
    # ========================================================

    duplicates = (
        base[
            [
                "CD_CVM",
                "ANO",
            ]
        ]
        .duplicated()
        .sum()
    )

    if duplicates:

        raise RuntimeError(
            "Duplicidade empresa-ano "
            "na base fundamental: "
            f"{duplicates}"
        )

    expected_rows = (
        companies[
            "CD_CVM"
        ].nunique()
        *
        len(years)
    )

    if len(base) != expected_rows:

        raise RuntimeError(
            "Grade empresa × ano incompleta. "
            f"Esperado={expected_rows}; "
            f"obtido={len(base)}."
        )

    return (
        base.sort_values(
            [
                "CD_CVM",
                "ANO",
            ]
        ).reset_index(drop=True),

        coverage.sort_values(
            "CD_CVM"
        ).reset_index(drop=True),
    )


# ============================================================
# 8. REGRESSION AUDIT — ESTUDO ORIGINAL
# ============================================================

def audit_frozen_study(
    base: pd.DataFrame,
    coverage: pd.DataFrame,
) -> None:

    """
    Executar somente contra os dados congelados
    2019–2025 do estudo original.

    Esperado:
        568 empresas
        7 anos
        3976 empresa-anos
        414 empresas elegíveis em dados
    """

    companies = (
        base["CD_CVM"].nunique()
    )

    years = sorted(
        base["ANO"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    eligible = int(
        coverage[
            "ELEGIVEL_DADOS_QUALITY"
        ].sum()
    )

    if companies != 568:

        raise AssertionError(
            f"Benchmark: esperado 568 "
            f"empresas; obtido {companies}."
        )

    if years != list(
        range(2019, 2026)
    ):

        raise AssertionError(
            "Benchmark: anos diferentes "
            "de 2019–2025."
        )

    if len(base) != 3976:

        raise AssertionError(
            f"Benchmark: esperado 3976 "
            f"empresa-anos; obtido "
            f"{len(base)}."
        )

    if eligible != 414:

        raise AssertionError(
            f"Benchmark: esperado 414 "
            f"elegíveis; obtido "
            f"{eligible}."
        )


# ============================================================
# 9. SELF TEST
# ============================================================

def _self_test():

    assert (
        normalize_text("ÚLTIMO")
        ==
        "ULTIMO"
    )

    assert (
        normalize_text(
            "Patrimônio Líquido Consolidado"
        )
        ==
        "PATRIMONIO LIQUIDO CONSOLIDADO"
    )

    assert (
        normalize_text(
            "Lucro/Prejuízo Consolidado do Período"
        )
        ==
        "LUCRO/PREJUIZO CONSOLIDADO DO PERIODO"
    )

    assert len(
        FINANCIAL_ENGINES
    ) == 3

    print(
        "cvm_fundamental_base_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
