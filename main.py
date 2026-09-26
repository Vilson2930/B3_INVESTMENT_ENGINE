# ============================================================
# B3_INVESTMENT_ENGINE
# main.py
#
# Orquestrador principal do sistema
#
# Fluxo oficial:
#
# Fundamental Engine
#        ↓
# Technical Timing Engine
#        ↓
# Integration Engine
#        ↓
# Resultado Final
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
# O GitHub Actions posteriormente alimentará estes arquivos.
#
# fundamental_input.csv
#
# Colunas mínimas:
#
# TICKER
# QUALITY_SCORE
# HISTORY_YEARS
# AVG_DAILY_LIQUIDITY_BRL
# VALUATION_SCORE
#
#
# technical_prices.csv
#
# Colunas mínimas:
#
# TICKER
# DATE
# OPEN
# HIGH
# LOW
# CLOSE
#
# ============================================================

FUNDAMENTAL_INPUT_FILE = (
    DATA_DIR /
    "fundamental_input.csv"
)

TECHNICAL_PRICES_FILE = (
    DATA_DIR /
    "technical_prices.csv"
)


# ============================================================
# 2. ARQUIVOS DE SAÍDA
# ============================================================

FINAL_RESULTS_FILE = (
    FINAL_REPORT_DIR /
    "b3_investment_engine_results.csv"
)

FINAL_TOP_FILE = (
    FINAL_REPORT_DIR /
    "b3_investment_engine_eligible.csv"
)

RUN_SUMMARY_FILE = (
    FINAL_REPORT_DIR /
    "run_summary.json"
)

LATEST_CHECKPOINT_FILE = (
    CHECKPOINTS_DIR /
    "latest_integrated_results.csv"
)


# ============================================================
# 3. COLUNAS OBRIGATÓRIAS
# ============================================================

FUNDAMENTAL_REQUIRED_COLUMNS = [
    "TICKER",
    "QUALITY_SCORE",
    "HISTORY_YEARS",
    "AVG_DAILY_LIQUIDITY_BRL",
    "VALUATION_SCORE",
]

TECHNICAL_REQUIRED_COLUMNS = [
    "TICKER",
    "DATE",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
]


# ============================================================
# 4. VALIDAR COLUNAS
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
# 5. CARREGAR FUNDAMENTOS
# ============================================================

def load_fundamental_input() -> pd.DataFrame:

    if not FUNDAMENTAL_INPUT_FILE.exists():

        raise FileNotFoundError(
            "\nArquivo fundamental não encontrado:\n"
            f"{FUNDAMENTAL_INPUT_FILE}\n\n"
            "O pipeline de dados deverá gerar "
            "fundamental_input.csv antes da execução."
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
        "fundamental_input.csv",
    )

    df["TICKER"] = (
        df["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    if df["TICKER"].duplicated().any():

        duplicated = (
            df.loc[
                df["TICKER"].duplicated(
                    keep=False
                ),
                "TICKER"
            ]
            .drop_duplicates()
            .tolist()
        )

        raise ValueError(
            "Tickers duplicados em "
            "fundamental_input.csv: "
            f"{duplicated}"
        )

    return df


# ============================================================
# 6. CARREGAR PREÇOS
# ============================================================

def load_technical_prices() -> pd.DataFrame:

    if not TECHNICAL_PRICES_FILE.exists():

        raise FileNotFoundError(
            "\nArquivo técnico não encontrado:\n"
            f"{TECHNICAL_PRICES_FILE}\n\n"
            "O pipeline de preços deverá gerar "
            "technical_prices.csv antes da execução."
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

    df = (
        df
        .dropna(
            subset=[
                "TICKER",
                "DATE",
            ]
        )
        .sort_values(
            [
                "TICKER",
                "DATE",
            ]
        )
        .reset_index(drop=True)
    )

    return df


# ============================================================
# 7. EXECUTAR FUNDAMENTAL ENGINE
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
# 8. SELECIONAR PREÇOS DO TICKER
# ============================================================

def get_ticker_prices(
    prices: pd.DataFrame,
    ticker: str,
) -> pd.DataFrame:

    ticker_prices = (
        prices.loc[
            prices["TICKER"]
            ==
            ticker,
            [
                "DATE",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
            ]
        ]
        .copy()
        .sort_values("DATE")
        .reset_index(drop=True)
    )

    return ticker_prices


# ============================================================
# 9. PROCESSAR UMA EMPRESA
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
    # PREÇOS
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
    # Se o fundamental estiver reprovado,
    # evaluate_ticker() devolve NOT_APPLICABLE.
    #
    # Portanto o técnico jamais recupera uma empresa.
    # --------------------------------------------------------

    if ticker_prices.empty:

        # Ainda chamamos o Technical Engine quando
        # fundamental estiver reprovado, pois nesse caso
        # ele não precisa da série de preços.

        if not fundamental_result.fundamental_approved:

            technical_result = evaluate_ticker(

                ticker=ticker,

                prices=pd.DataFrame(),

                fundamental_approved=False,
            )

        else:

            # Empresa fundamentalmente aprovada, mas sem
            # preços disponíveis.
            #
            # Importante:
            # isso NÃO torna a empresa inelegível.
            #
            # Criamos o resultado técnico indisponível
            # usando a mesma estrutura oficial.

            from technical_engine import TechnicalResult

            technical_result = TechnicalResult(

                ticker=ticker,

                technical_available=False,

                technical_role=(
                    "ENTRY_CONTEXT"
                ),

                technical_engine_version=(
                    "FINAL_V1"
                ),

                technical_engine_mode=(
                    "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT"
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
                    "SEM_DADOS_DE_PRECO"
                ),
            )

    else:

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
# 10. EXECUTAR SISTEMA COMPLETO
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
        "Registros de preços:",
        len(prices_df)
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
    # 11. RANKING
    # ========================================================
    #
    # O ranking continua FUNDAMENTAL.
    #
    # Nenhum indicador técnico participa da ordenação.
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

    # Rank apenas entre elegíveis.
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
    # 12. TESTES DE INTEGRIDADE
    # ========================================================

    # Técnico nunca pode criar score.
    technical_score_violation = (
        results_df[
            "TECHNICAL_SCORE"
        ]
        .notna()
        .sum()
    )

    # Nenhum gatilho obrigatório.
    mandatory_trigger_violation = (
        results_df[
            "MANDATORY_TRIGGER"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    # Nenhum gatilho OOS validado.
    oos_trigger_violation = (
        results_df[
            "VALIDATED_OOS_TRIGGER"
        ]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    # Empresa fundamentalmente reprovada
    # jamais pode ficar elegível.
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

    assert (
        technical_score_violation
        ==
        0
    )

    assert (
        mandatory_trigger_violation
        ==
        0
    )

    assert (
        oos_trigger_violation
        ==
        0
    )

    assert (
        rescue_violation
        ==
        0
    )

    # ========================================================
    # 13. SALVAR RESULTADO COMPLETO
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
    # 14. SALVAR SOMENTE ELEGÍVEIS
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
    # 15. RESUMO DA EXECUÇÃO
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

        "architecture":
            "FUNDAMENTAL_FIRST",
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
    # 16. LOG DE ERROS
    # ========================================================

    if errors:

        error_file = (
            LOGS_DIR /
            "processing_errors.csv"
        )

        pd.DataFrame(
            errors
        ).to_csv(
            error_file,
            index=False,
            encoding="utf-8-sig",
        )

    # ========================================================
    # 17. RESULTADO
    # ========================================================

    print("\n" + "=" * 80)
    print("RESULTADO DA EXECUÇÃO")
    print("=" * 80)

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
        "\nTechnical Score criado: NÃO"
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
    # 18. TOP FUNDAMENTAL
    # ========================================================

    print("\n" + "=" * 80)
    print("TOP FUNDAMENTAL")
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
        "✓ Fundamental Engine executado."
    )

    print(
        "✓ Technical Timing Engine executado."
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
# 19. EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    run_engine()
