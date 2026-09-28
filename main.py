# ============================================================
# B3_INVESTMENT_ENGINE
# main.py
#
# Orquestrador principal do sistema
#
# Fluxo oficial:
#
# Fundamental Engine LIVE
#        ↓
# Technical Timing Engine — Cell06B congelado
#        ↓
# Integration Engine
#        ↓
# Resultado Final
#
# ARQUITETURA:
# FUNDAMENTAL FIRST + TECHNICAL CONTEXT
#
# IMPORTANTE:
#
# - Fundamentos: LIVE
# - Técnico: Cell06B congelado
# - Técnico NÃO altera ranking
# - Técnico NÃO cria score
# - Técnico NÃO cria gatilho obrigatório
# - Técnico NÃO recupera empresa reprovada
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
import json

import pandas as pd

from config import (
    PROJECT_NAME,
    PROJECT_VERSION,
    DATA_DIR,
    CHECKPOINTS_DIR,
    LOGS_DIR,
    FINAL_REPORT_DIR,
    validate_config,
)

from fundamental_engine import (
    FundamentalInput,
    evaluate_company,
)

from technical_engine import (
    evaluate_ticker,
)

from integration_engine import (
    integrate,
    result_to_dict,
)


# ============================================================
# 1. ARQUIVOS DE ENTRADA
# ============================================================
#
# FUNDAMENTAL:
# produzido por build_live_fundamental_input.py
#
# TÉCNICO:
# produzido pelo build_technical_prices.py atual,
# preservando exatamente o checkpoint Cell06B congelado.
# ============================================================

LIVE_DATA_DIR = (
    DATA_DIR
    / "live"
)

LIVE_FUNDAMENTAL_DIR = (
    LIVE_DATA_DIR
    / "fundamental"
)

FUNDAMENTAL_INPUT_FILE = (
    LIVE_FUNDAMENTAL_DIR
    / "fundamental_input_live.csv"
)

TECHNICAL_PRICES_FILE = (
    DATA_DIR
    / "technical_prices.csv"
)


# ============================================================
# 2. ARQUIVOS DE SAÍDA
# ============================================================

FINAL_RESULTS_FILE = (
    FINAL_REPORT_DIR
    / "b3_investment_engine_results.csv"
)

FINAL_TOP_FILE = (
    FINAL_REPORT_DIR
    / "b3_investment_engine_eligible.csv"
)

RUN_SUMMARY_FILE = (
    FINAL_REPORT_DIR
    / "run_summary.json"
)

LATEST_CHECKPOINT_FILE = (
    CHECKPOINTS_DIR
    / "latest_integrated_results.csv"
)


# ============================================================
# 3. COLUNAS OBRIGATÓRIAS — FUNDAMENTAL LIVE
# ============================================================

FUNDAMENTAL_REQUIRED_COLUMNS = [
    "TICKER",
    "QUALITY_SCORE",
    "HISTORY_YEARS",
    "AVG_DAILY_LIQUIDITY_BRL",
    "VALUATION_SCORE",
]


# ============================================================
# 4. COLUNAS TÉCNICAS
# ============================================================
#
# Base técnica congelada derivada do Cell06B.
#
# Os 7 indicadores já chegam calculados.
#
# main.py:
#
# - NÃO recalcula indicadores;
# - NÃO altera indicadores;
# - NÃO cria Technical Score.
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

TECHNICAL_REQUIRED_COLUMNS = [
    "CD_CVM",
    "TICKER",
    "DATE",
    "TECH_SEGMENT_ID",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    *TECHNICAL_INDICATORS,
]


# ============================================================
# 5. VALIDAR COLUNAS
# ============================================================

def validate_columns(
    df: pd.DataFrame,
    required_columns: list,
    source_name: str,
):

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            f"{source_name}: "
            f"colunas obrigatórias ausentes: "
            f"{missing}"
        )

    return True


# ============================================================
# 6. CARREGAR FUNDAMENTOS LIVE
# ============================================================

def load_fundamental_input() -> pd.DataFrame:

    if not FUNDAMENTAL_INPUT_FILE.exists():

        raise FileNotFoundError(
            "\nArquivo fundamental LIVE não encontrado:\n\n"
            f"{FUNDAMENTAL_INPUT_FILE}\n\n"
            "Execute primeiro:\n"
            "build_live_fundamental_input.py"
        )

    print("\n" + "=" * 80)
    print("CARREGANDO FUNDAMENTOS LIVE")
    print("=" * 80)

    print(
        "Arquivo:",
        FUNDAMENTAL_INPUT_FILE,
    )

    df = pd.read_csv(
        FUNDAMENTAL_INPUT_FILE,
        low_memory=False,
    )

    df.columns = [
        str(column)
        .strip()
        .upper()

        for column in df.columns
    ]

    validate_columns(
        df,
        FUNDAMENTAL_REQUIRED_COLUMNS,
        "fundamental_input_live.csv",
    )

    df["TICKER"] = (
        df["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    numeric_columns = [
        "QUALITY_SCORE",
        "HISTORY_YEARS",
        "AVG_DAILY_LIQUIDITY_BRL",
        "VALUATION_SCORE",
    ]

    if "FUNDAMENTAL_SCORE" in df.columns:
        numeric_columns.append(
            "FUNDAMENTAL_SCORE"
        )

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "TICKER",
            "QUALITY_SCORE",
            "HISTORY_YEARS",
            "AVG_DAILY_LIQUIDITY_BRL",
            "VALUATION_SCORE",
        ]
    ).copy()

    if df["TICKER"].duplicated().any():

        duplicated = (
            df.loc[
                df["TICKER"].duplicated(
                    keep=False
                ),
                "TICKER",
            ]
            .drop_duplicates()
            .tolist()
        )

        raise ValueError(
            "Tickers duplicados em "
            "fundamental_input_live.csv: "
            f"{duplicated}"
        )

    print(
        "Empresas fundamentais LIVE:",
        len(df),
    )

    print(
        "Tickers únicos:",
        df["TICKER"].nunique(),
    )

    return df


# ============================================================
# 7. CARREGAR BASE TÉCNICA
# ============================================================
#
# IMPORTANTE:
#
# A etapa técnica ainda utiliza o checkpoint Cell06B congelado.
#
# Esta função:
#
# - NÃO recalcula indicadores;
# - NÃO altera segmentação;
# - NÃO preenche indicadores ausentes.
# ============================================================

def load_technical_prices() -> pd.DataFrame:

    if not TECHNICAL_PRICES_FILE.exists():

        raise FileNotFoundError(
            "\nArquivo técnico não encontrado:\n\n"
            f"{TECHNICAL_PRICES_FILE}\n\n"
            "Execute primeiro:\n"
            "build_technical_prices.py"
        )

    print("\n" + "=" * 80)
    print("CARREGANDO CONTEXTO TÉCNICO")
    print("=" * 80)

    print(
        "Fonte técnica:",
        "CELL06B_FROZEN",
    )

    print(
        "Arquivo:",
        TECHNICAL_PRICES_FILE,
    )

    df = pd.read_csv(
        TECHNICAL_PRICES_FILE,
        low_memory=False,
    )

    df.columns = [
        str(column)
        .strip()
        .upper()

        for column in df.columns
    ]

    validate_columns(
        df,
        TECHNICAL_REQUIRED_COLUMNS,
        "technical_prices.csv",
    )

    df["TICKER"] = (
        df["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["DATE"] = pd.to_datetime(
        df["DATE"],
        errors="coerce",
    )

    df["CD_CVM"] = pd.to_numeric(
        df["CD_CVM"],
        errors="coerce",
    )

    for column in [
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        *TECHNICAL_INDICATORS,
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = (
        df
        .dropna(
            subset=[
                "CD_CVM",
                "TICKER",
                "DATE",
                "TECH_SEGMENT_ID",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
            ]
        )
        .sort_values(
            [
                "TICKER",
                "DATE",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    print(
        "Registros técnicos:",
        len(df),
    )

    print(
        "Tickers técnicos:",
        df["TICKER"].nunique(),
    )

    return df


# ============================================================
# 8. EXECUTAR FUNDAMENTAL ENGINE
# ============================================================

def run_fundamental_engine(
    row: pd.Series
):

    data = FundamentalInput(

        ticker=row["TICKER"],

        quality_score=(
            row["QUALITY_SCORE"]
        ),

        history_years=(
            row["HISTORY_YEARS"]
        ),

        avg_daily_liquidity_brl=(
            row[
                "AVG_DAILY_LIQUIDITY_BRL"
            ]
        ),

        valuation_score=(
            row["VALUATION_SCORE"]
        ),
    )

    return evaluate_company(
        data
    )


# ============================================================
# 9. SELECIONAR DADOS TÉCNICOS DO TICKER
# ============================================================

def get_ticker_prices(
    prices: pd.DataFrame,
    ticker: str,
) -> pd.DataFrame:

    columns = [
        "CD_CVM",
        "TICKER",
        "DATE",
        "TECH_SEGMENT_ID",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        *TECHNICAL_INDICATORS,
    ]

    ticker_prices = (
        prices.loc[
            prices["TICKER"]
            ==
            ticker,
            columns,
        ]
        .copy()
        .sort_values("DATE")
        .reset_index(drop=True)
    )

    return ticker_prices


# ============================================================
# 10. PROCESSAR UMA EMPRESA
# ============================================================

def process_company(
    row: pd.Series,
    prices: pd.DataFrame,
):

    ticker = str(
        row["TICKER"]
    ).strip().upper()

    # --------------------------------------------------------
    # FUNDAMENTAL
    # --------------------------------------------------------

    fundamental_result = (
        run_fundamental_engine(
            row
        )
    )

    # --------------------------------------------------------
    # BASE TÉCNICA
    # --------------------------------------------------------

    ticker_prices = (
        get_ticker_prices(
            prices,
            ticker,
        )
    )

    # --------------------------------------------------------
    # TECHNICAL
    # --------------------------------------------------------
    #
    # O motor técnico:
    #
    # - não recalcula indicadores;
    # - não cria score;
    # - não cria gatilho obrigatório;
    # - não veta fundamento aprovado;
    # - não recupera fundamento reprovado.
    # --------------------------------------------------------

    technical_result = evaluate_ticker(

        ticker=ticker,

        prices=ticker_prices,

        fundamental_approved=(
            fundamental_result
            .fundamental_approved
        ),
    )

    # --------------------------------------------------------
    # INTEGRAÇÃO
    # --------------------------------------------------------

    integrated_result = integrate(

        fundamental_result,

        technical_result,
    )

    return integrated_result


# ============================================================
# 11. EXECUTAR SISTEMA COMPLETO
# ============================================================

def run_engine():

    print("=" * 80)
    print(PROJECT_NAME)
    print(f"VERSÃO {PROJECT_VERSION}")
    print("=" * 80)

    validate_config()

    print(
        "\n✓ Configuração validada."
    )

    # --------------------------------------------------------
    # DADOS
    # --------------------------------------------------------

    fundamental_df = (
        load_fundamental_input()
    )

    prices_df = (
        load_technical_prices()
    )

    print(
        "\nEmpresas recebidas:",
        len(fundamental_df)
    )

    print(
        "Registros técnicos:",
        len(prices_df)
    )

    print(
        "Indicadores técnicos:",
        len(TECHNICAL_INDICATORS)
    )

    # --------------------------------------------------------
    # PROCESSAMENTO
    # --------------------------------------------------------

    results = []

    errors = []

    for _, row in fundamental_df.iterrows():

        ticker = str(
            row["TICKER"]
        ).strip().upper()

        try:

            integrated = process_company(

                row=row,

                prices=prices_df,
            )

            results.append(
                result_to_dict(
                    integrated
                )
            )

        except Exception as exc:

            errors.append({

                "TICKER":
                    ticker,

                "ERROR":
                    str(exc),
            })

            print(
                f"ERRO {ticker}: {exc}"
            )

    # --------------------------------------------------------
    # PROTEÇÃO
    # --------------------------------------------------------

    if not results:

        raise RuntimeError(
            "Nenhuma empresa foi processada "
            "com sucesso."
        )

    results_df = pd.DataFrame(
        results
    )

    # ========================================================
    # 12. RANKING
    # ========================================================
    #
    # Ranking continua 100% FUNDAMENTAL.
    #
    # Técnico NÃO participa da ordenação.
    # ========================================================

    results_df[
        "FUNDAMENTAL_SCORE"
    ] = pd.to_numeric(
        results_df[
            "FUNDAMENTAL_SCORE"
        ],
        errors="coerce",
    )

    results_df = (
        results_df
        .sort_values(
            [
                "ELIGIBLE",
                "FUNDAMENTAL_SCORE",
            ],
            ascending=[
                False,
                False,
            ],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Rank somente entre elegíveis
    # --------------------------------------------------------

    results_df[
        "FUNDAMENTAL_RANK"
    ] = pd.NA

    eligible_mask = (
        results_df["ELIGIBLE"]
        ==
        True
    )

    eligible_indexes = (
        results_df.loc[
            eligible_mask
        ]
        .sort_values(
            "FUNDAMENTAL_SCORE",
            ascending=False,
        )
        .index
        .tolist()
    )

    for rank, index in enumerate(
        eligible_indexes,
        start=1,
    ):

        results_df.loc[
            index,
            "FUNDAMENTAL_RANK"
        ] = rank

    # ========================================================
    # 13. TESTES DE INTEGRIDADE
    # ========================================================

    required_integrity_columns = [
        "TECHNICAL_SCORE",
        "MANDATORY_TRIGGER",
        "VALIDATED_OOS_TRIGGER",
        "FUNDAMENTAL_APPROVED",
        "ELIGIBLE",
    ]

    validate_columns(
        results_df,
        required_integrity_columns,
        "resultado integrado",
    )

    technical_score_violation = (
        results_df[
            "TECHNICAL_SCORE"
        ]
        .notna()
        .sum()
    )

    mandatory_trigger_violation = (
        results_df[
            "MANDATORY_TRIGGER"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    oos_trigger_violation = (
        results_df[
            "VALIDATED_OOS_TRIGGER"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    rescue_violation = (

        (
            results_df[
                "FUNDAMENTAL_APPROVED"
            ]
            ==
            False
        )

        &

        (
            results_df[
                "ELIGIBLE"
            ]
            ==
            True
        )

    ).sum()

    if technical_score_violation != 0:

        raise RuntimeError(
            "Violação metodológica: "
            "Technical Score foi criado."
        )

    if mandatory_trigger_violation != 0:

        raise RuntimeError(
            "Violação metodológica: "
            "gatilho técnico obrigatório encontrado."
        )

    if oos_trigger_violation != 0:

        raise RuntimeError(
            "Violação metodológica: "
            "gatilho OOS encontrado."
        )

    if rescue_violation != 0:

        raise RuntimeError(
            "Violação metodológica: "
            "técnico recuperou empresa "
            "fundamentalmente reprovada."
        )

    # ========================================================
    # 14. SALVAR RESULTADO COMPLETO
    # ========================================================

    FINAL_REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    CHECKPOINTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_df.to_csv(
        FINAL_RESULTS_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    results_df.to_csv(
        LATEST_CHECKPOINT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # 15. SALVAR SOMENTE ELEGÍVEIS
    # ========================================================

    eligible_df = (
        results_df.loc[
            results_df[
                "ELIGIBLE"
            ]
            ==
            True
        ]
        .copy()
        .sort_values(
            "FUNDAMENTAL_SCORE",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    eligible_df.to_csv(
        FINAL_TOP_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # 16. RESUMO DA EXECUÇÃO
    # ========================================================

    technical_available = int(
        eligible_df[
            "TECHNICAL_AVAILABLE"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    summary = {

        "project":
            PROJECT_NAME,

        "version":
            PROJECT_VERSION,

        "executed_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "fundamental_data_mode":
            "LIVE",

        "fundamental_input_file":
            str(
                FUNDAMENTAL_INPUT_FILE
            ),

        "technical_data_mode":
            "CELL06B_FROZEN",

        "technical_input_file":
            str(
                TECHNICAL_PRICES_FILE
            ),

        "companies_received":
            int(
                len(
                    fundamental_df
                )
            ),

        "companies_processed":
            int(
                len(
                    results_df
                )
            ),

        "processing_errors":
            int(
                len(
                    errors
                )
            ),

        "fundamental_eligible":
            int(
                len(
                    eligible_df
                )
            ),

        "technical_context_available":
            technical_available,

        "technical_context_unavailable":
            int(
                len(
                    eligible_df
                )
                -
                technical_available
            ),

        "technical_score_created":
            False,

        "mandatory_technical_trigger":
            False,

        "oos_validated_trigger_count":
            0,

        "ranking_method":
            "FUNDAMENTAL_SCORE",

        "technical_used_in_ranking":
            False,

        "technical_indicator_source":
            "CELL06B_FROZEN",

        "technical_indicators_recalculated":
            False,

        "architecture":
            "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT",
    }

    with open(
        RUN_SUMMARY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )

    # ========================================================
    # 17. LOG DE ERROS
    # ========================================================

    if errors:

        LOGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        error_file = (
            LOGS_DIR
            / "processing_errors.csv"
        )

        pd.DataFrame(
            errors
        ).to_csv(
            error_file,
            index=False,
            encoding="utf-8-sig",
        )

    # ========================================================
    # 18. RESULTADO
    # ========================================================

    print("\n" + "=" * 80)
    print("RESULTADO DA EXECUÇÃO")
    print("=" * 80)

    print(
        "Fundamental:",
        "LIVE",
    )

    print(
        "Técnico:",
        "CELL06B CONGELADO",
    )

    print(
        "Empresas recebidas:",
        len(fundamental_df)
    )

    print(
        "Empresas processadas:",
        len(results_df)
    )

    print(
        "Erros:",
        len(errors)
    )

    print(
        "Elegíveis pelos fundamentos:",
        len(eligible_df)
    )

    print(
        "Com contexto técnico:",
        technical_available
    )

    print(
        "Sem contexto técnico:",
        len(eligible_df)
        -
        technical_available
    )

    print(
        "\nIndicadores recalculados: NÃO"
    )

    print(
        "Technical Score criado: NÃO"
    )

    print(
        "Técnico participa do ranking: NÃO"
    )

    print(
        "Gatilho técnico obrigatório: NÃO"
    )

    print(
        "Técnico recupera empresa reprovada: NÃO"
    )

    # ========================================================
    # 19. TOP FUNDAMENTAL
    # ========================================================

    print("\n" + "=" * 80)
    print("TOP FUNDAMENTAL — LIVE")
    print("=" * 80)

    columns = [
        "FUNDAMENTAL_RANK",
        "TICKER",
        "QUALITY_SCORE",
        "VALUATION_SCORE",
        "FUNDAMENTAL_SCORE",
        "TECHNICAL_AVAILABLE",
        "TECHNICAL_OBSERVATIONS",
    ]

    available_columns = [
        column
        for column in columns
        if column in eligible_df.columns
    ]

    if len(eligible_df) > 0:

        print(
            eligible_df[
                available_columns
            ]
            .head(20)
            .to_string(
                index=False
            )
        )

    else:

        print(
            "Nenhuma empresa elegível."
        )

    print("\n" + "=" * 80)

    print(
        "✓ Fundamental Engine LIVE executado."
    )

    print(
        "✓ Technical Timing Engine executado."
    )

    print(
        "✓ Indicadores técnicos Cell06B preservados."
    )

    print(
        "✓ Integration Engine executado."
    )

    print(
        "✓ Ranking fundamental preservado."
    )

    print(
        "✓ Resultado integrado salvo."
    )

    print("=" * 80)

    print(
        "\nResultado completo:",
        FINAL_RESULTS_FILE
    )

    print(
        "\nElegíveis:",
        FINAL_TOP_FILE
    )

    print(
        "\nResumo:",
        RUN_SUMMARY_FILE
    )

    return results_df


# ============================================================
# 20. EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    run_engine()
