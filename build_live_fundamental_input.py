"""
B3 INVESTMENT ENGINE
BUILD LIVE FUNDAMENTAL INPUT — V2

Orquestrador fundamental de produção.

Fluxo preservado:
CVM DFP -> Identity -> FCA -> Sector -> Fundamental Base -> Indicators
-> Quality -> B3 Investability -> Valuation -> 70% Quality / 30% Valuation.

A metodologia V1 permanece congelada. Este módulo apenas conecta os motores
já validados e falha de forma segura quando uma camada de dados ainda não está
pronta.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cvm_statement_loader_v1 import load_dfp_history
from live_identity_engine import run_live_identity_engine
from live_fca_engine import run_live_fca_engine
from sector_engine_v1 import run_sector_engine
from cvm_fundamental_base_v1 import build_cvm_fundamental_base
from fundamental_indicators_v1 import run_fundamental_indicators
from quality_engine_v1 import run_quality_engine, split_quality_results
from b3_investability_v1 import (
    live_config,
    run_b3_investability,
    get_investability_approved,
)
from valuation_engine_v1 import run_valuation_engine


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"

CVM_DIR = LIVE_DIR / "cvm"
PROCESSED_DIR = LIVE_DIR / "processed"
B3_DIR = LIVE_DIR / "b3"

OUTPUT_DIR = LIVE_DIR / "fundamental"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CVM_MANIFEST = CVM_DIR / "cvm_manifest.json"

SECURITY_HISTORY_FILE = (
    PROCESSED_DIR / "fca_security_history.csv"
)

MARKET_HISTORY_FILE = (
    B3_DIR / "market_history_live.csv"
)

VALUATION_BASE_FILE = (
    OUTPUT_DIR / "valuation_base_live.csv"
)

OUTPUT_FILE = (
    OUTPUT_DIR / "fundamental_input_live.csv"
)

OUTPUT_MANIFEST = (
    OUTPUT_DIR / "fundamental_live_manifest.json"
)

QUALITY_FILE = (
    OUTPUT_DIR / "quality_live.csv"
)

QUALITY_APPROVED_FILE = (
    OUTPUT_DIR / "quality_approved_live.csv"
)

INVESTABILITY_FILE = (
    OUTPUT_DIR / "investability_live.csv"
)

INVESTABILITY_APPROVED_FILE = (
    OUTPUT_DIR / "investability_approved_live.csv"
)

VALUATION_FILE = (
    OUTPUT_DIR / "valuation_live.csv"
)


# ============================================================
# METODOLOGIA CONGELADA
# ============================================================

METHODOLOGY_VERSION = "B3_FUNDAMENTAL_V1"

QUALITY_GATE = 60.0

MIN_HISTORY_YEARS = 10.0

MIN_AVG_DAILY_LIQUIDITY_BRL = 6_000_000.0

QUALITY_WEIGHT = 0.70

VALUATION_WEIGHT = 0.30


# ============================================================
# EXCEPTIONS
# ============================================================

class LiveFundamentalError(RuntimeError):
    pass


class DataInsufficientError(LiveFundamentalError):
    pass


class MethodologyIntegrityError(
    LiveFundamentalError
):
    pass


# ============================================================
# UTILITIES
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_json_atomic(
    data: dict,
    path: Path,
) -> None:

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def write_csv_atomic(
    df: pd.DataFrame,
    path: Path,
) -> None:

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    df.to_csv(
        tmp,
        index=False,
        encoding="utf-8-sig",
    )

    tmp.replace(path)


# ============================================================
# AUDITORIA DA METODOLOGIA
# ============================================================

def audit_frozen_methodology() -> None:

    checks = {

        "QUALITY_GATE":
            QUALITY_GATE == 60.0,

        "MIN_HISTORY_YEARS":
            MIN_HISTORY_YEARS == 10.0,

        "MIN_AVG_DAILY_LIQUIDITY_BRL":
            MIN_AVG_DAILY_LIQUIDITY_BRL
            == 6_000_000.0,

        "QUALITY_WEIGHT":
            QUALITY_WEIGHT == 0.70,

        "VALUATION_WEIGHT":
            VALUATION_WEIGHT == 0.30,

        "WEIGHT_SUM":
            abs(
                QUALITY_WEIGHT
                + VALUATION_WEIGHT
                - 1.0
            ) <= 1e-12,
    }

    failed = [
        name
        for name, ok
        in checks.items()
        if not ok
    ]

    if failed:

        raise MethodologyIntegrityError(
            "Metodologia V1 alterada: "
            + ", ".join(failed)
        )


# ============================================================
# AUDITORIA DOS DADOS CVM
# ============================================================

def audit_cvm_data() -> None:

    if not CVM_MANIFEST.exists():

        raise DataInsufficientError(
            "Manifest CVM não encontrado: "
            f"{CVM_MANIFEST}"
        )

    if not (
        CVM_DIR / "cad_cia_aberta.csv"
    ).exists():

        raise DataInsufficientError(
            "Cadastro oficial CVM "
            "não encontrado."
        )

    if not (
        CVM_DIR / "dfp"
    ).exists():

        raise DataInsufficientError(
            "Diretório DFP não encontrado."
        )

    if not (
        CVM_DIR / "fca"
    ).exists():

        raise DataInsufficientError(
            "Diretório FCA não encontrado."
        )


# ============================================================
# B3 MARKET HISTORY
# ============================================================

def _load_market_history() -> pd.DataFrame:

    if not MARKET_HISTORY_FILE.exists():

        raise DataInsufficientError(
            "Camada B3 normalizada ainda "
            "não encontrada: "
            f"{MARKET_HISTORY_FILE}. "
            "É necessário gerar TICKER, "
            "DATA e VOLTOT com COTAHIST "
            "histórico + B3 ano corrente."
        )

    market = pd.read_csv(
        MARKET_HISTORY_FILE,
        low_memory=False,
    )

    required = {
        "TICKER",
        "DATA",
        "VOLTOT",
    }

    missing = (
        required
        - set(market.columns)
    )

    if missing:

        raise DataInsufficientError(
            "market_history_live.csv "
            "sem colunas: "
            + ", ".join(
                sorted(missing)
            )
        )

    market["DATA"] = pd.to_datetime(
        market["DATA"],
        errors="coerce",
    )

    market["VOLTOT"] = pd.to_numeric(
        market["VOLTOT"],
        errors="coerce",
    )

    market["TICKER"] = (
        market["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    market = market.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    if market.empty:

        raise DataInsufficientError(
            "market_history_live.csv "
            "está vazio após validação."
        )

    return market


# ============================================================
# FCA — HISTÓRICO DE TICKERS
# ============================================================

def _load_ticker_history() -> pd.DataFrame:

    if not SECURITY_HISTORY_FILE.exists():

        raise DataInsufficientError(
            "Histórico FCA de tickers "
            "não encontrado: "
            f"{SECURITY_HISTORY_FILE}"
        )

    fca = pd.read_csv(
        SECURITY_HISTORY_FILE,
        low_memory=False,
    )

    cd_candidates = [
        "CD_CVM",
        "CODIGO_CVM",
    ]

    ticker_candidates = [
        "CODIGO_NEGOCIACAO",
        "CODIGO_NEGOCIACAO_VALOR_MOBILIARIO",
        "TICKER",
        "COD_NEGOCIACAO",
    ]

    cd_col = next(
        (
            c
            for c
            in cd_candidates
            if c in fca.columns
        ),
        None,
    )

    ticker_col = next(
        (
            c
            for c
            in ticker_candidates
            if c in fca.columns
        ),
        None,
    )

    if (
        cd_col is None
        or ticker_col is None
    ):

        raise DataInsufficientError(
            "fca_security_history.csv "
            "sem CD_CVM/ticker compatível."
        )

    out = fca[
        [
            cd_col,
            ticker_col,
        ]
    ].copy()

    out.columns = [
        "CD_CVM",
        "TICKER",
    ]

    out["CD_CVM"] = pd.to_numeric(
        out["CD_CVM"],
        errors="coerce",
    )

    out["TICKER"] = (
        out["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    out = (
        out
        .dropna(
            subset=[
                "CD_CVM",
                "TICKER",
            ]
        )
        .drop_duplicates()
    )

    return out


# ============================================================
# VALUATION BASE
# ============================================================

def _load_valuation_base() -> pd.DataFrame:

    if not VALUATION_BASE_FILE.exists():

        raise DataInsufficientError(
            "Base live de Valuation "
            "ainda não encontrada: "
            f"{VALUATION_BASE_FILE}."
        )

    return pd.read_csv(
        VALUATION_BASE_FILE,
        low_memory=False,
    )


# ============================================================
# VALIDAÇÃO DA SAÍDA
# ============================================================

def validate_live_output(
    df: pd.DataFrame,
) -> None:

    required = {

        "TICKER",

        "QUALITY_SCORE",

        "HISTORY_YEARS",

        "AVG_DAILY_LIQUIDITY_BRL",

        "VALUATION_SCORE",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        raise DataInsufficientError(
            "Saída live sem colunas "
            "obrigatórias: "
            + ", ".join(
                sorted(missing)
            )
        )

    if df.empty:

        raise DataInsufficientError(
            "Saída fundamental live vazia."
        )

    if (
        df["TICKER"].isna().any()
        or df["TICKER"].duplicated().any()
    ):

        raise MethodologyIntegrityError(
            "Ticker ausente ou duplicado "
            "na saída live."
        )

    q = pd.to_numeric(
        df["QUALITY_SCORE"],
        errors="coerce",
    )

    h = pd.to_numeric(
        df["HISTORY_YEARS"],
        errors="coerce",
    )

    l = pd.to_numeric(
        df[
            "AVG_DAILY_LIQUIDITY_BRL"
        ],
        errors="coerce",
    )

    if (
        q.isna().any()
        or h.isna().any()
        or l.isna().any()
    ):

        raise DataInsufficientError(
            "Quality/history/liquidez "
            "inválidos na saída live."
        )

    if (
        (q < QUALITY_GATE).any()
        or (
            h
            < MIN_HISTORY_YEARS
        ).any()
        or (
            l
            < MIN_AVG_DAILY_LIQUIDITY_BRL
        ).any()
    ):

        raise MethodologyIntegrityError(
            "Empresa fora dos gates "
            "entrou na saída live."
        )


# ============================================================
# SCORE FUNDAMENTAL 70 / 30
# ============================================================

def calculate_fundamental_score(
    df: pd.DataFrame,
) -> pd.DataFrame:

    out = df.copy()

    out["QUALITY_SCORE"] = (
        pd.to_numeric(
            out["QUALITY_SCORE"],
            errors="coerce",
        )
    )

    out["VALUATION_SCORE"] = (
        pd.to_numeric(
            out["VALUATION_SCORE"],
            errors="coerce",
        )
    )

    out["FUNDAMENTAL_SCORE"] = pd.NA

    mask = (
        out["QUALITY_SCORE"].notna()
        & out[
            "VALUATION_SCORE"
        ].notna()
    )

    out.loc[
        mask,
        "FUNDAMENTAL_SCORE",
    ] = (

        QUALITY_WEIGHT
        * out.loc[
            mask,
            "QUALITY_SCORE",
        ]

        +

        VALUATION_WEIGHT
        * out.loc[
            mask,
            "VALUATION_SCORE",
        ]
    )

    out[
        "FUNDAMENTAL_SCORE"
    ] = pd.to_numeric(
        out["FUNDAMENTAL_SCORE"],
        errors="coerce",
    )

    return out


# ============================================================
# PIPELINE FUNDAMENTAL LIVE
# ============================================================

def build_live_fundamental_input() -> pd.DataFrame:

    print("=" * 72)

    print(
        "B3 INVESTMENT ENGINE — "
        "LIVE FUNDAMENTAL V2"
    )

    print("=" * 72)

    # --------------------------------------------------------
    # AUDITORIAS
    # --------------------------------------------------------

    audit_frozen_methodology()

    audit_cvm_data()

    # --------------------------------------------------------
    # 1. DFP
    # --------------------------------------------------------

    print(
        "[1/8] Carregando "
        "DFP oficial..."
    )

    statements = load_dfp_history()

    dre = statements["DRE"]

    # --------------------------------------------------------
    # 2. IDENTITY + FCA
    # --------------------------------------------------------

    print(
        "[2/8] Identidade + FCA..."
    )

    identity = (
        run_live_identity_engine(
            dre,
            save_outputs=True,
        )
    )

    companies = (
        run_live_fca_engine(
            identity,
            save_outputs=True,
        )
    )

    # --------------------------------------------------------
    # 3. SECTOR
    # --------------------------------------------------------

    print(
        "[3/8] Sector Engine V1..."
    )

    architecture = (
        run_sector_engine(
            companies,
            dre,
        )
    )

    # --------------------------------------------------------
    # 4. FUNDAMENTAL BASE + INDICATORS
    # --------------------------------------------------------

    print(
        "[4/8] Fundamental Base "
        "+ Indicators V1..."
    )

    (
        fundamental_base,
        _coverage,
    ) = build_cvm_fundamental_base(
        architecture,
        statements,
    )

    (
        _raw,
        company_summary,
    ) = run_fundamental_indicators(
        fundamental_base
    )

    # --------------------------------------------------------
    # 5. QUALITY
    # --------------------------------------------------------

    print(
        "[5/8] Quality Engine V1..."
    )

    quality = run_quality_engine(
        company_summary
    )

    (
        quality_approved,
        _blocked,
    ) = split_quality_results(
        quality
    )

    write_csv_atomic(
        quality,
        QUALITY_FILE,
    )

    write_csv_atomic(
        quality_approved,
        QUALITY_APPROVED_FILE,
    )

    # --------------------------------------------------------
    # 6. INVESTABILITY
    # --------------------------------------------------------

    print(
        "[6/8] B3 Investability V1..."
    )

    ticker_history = (
        _load_ticker_history()
    )

    market_history = (
        _load_market_history()
    )

    latest_date = pd.to_datetime(
        market_history["DATA"],
        errors="coerce",
    ).max()

    if pd.isna(latest_date):

        raise DataInsufficientError(
            "Não foi possível determinar "
            "a última data B3."
        )

    config = live_config(
        latest_date,
        liquidity_reference_year=int(
            latest_date.year
        ),
    )

    investability = (
        run_b3_investability(
            quality_approved,
            ticker_history,
            market_history,
            config,
        )
    )

    investability_approved = (
        get_investability_approved(
            investability
        )
    )

    write_csv_atomic(
        investability,
        INVESTABILITY_FILE,
    )

    write_csv_atomic(
        investability_approved,
        INVESTABILITY_APPROVED_FILE,
    )

    # --------------------------------------------------------
    # 7. VALUATION
    # --------------------------------------------------------

    print(
        "[7/8] Valuation Engine V1..."
    )

    valuation_base = (
        _load_valuation_base()
    )

    approved_ids = set(
        pd.to_numeric(
            investability_approved[
                "CD_CVM"
            ],
            errors="coerce",
        ).dropna()
    )

    valuation_base[
        "CD_CVM"
    ] = pd.to_numeric(
        valuation_base["CD_CVM"],
        errors="coerce",
    )

    valuation_base = (
        valuation_base[
            valuation_base[
                "CD_CVM"
            ].isin(
                approved_ids
            )
        ]
        .copy()
    )

    valuation = (
        run_valuation_engine(
            valuation_base
        )
    )

    write_csv_atomic(
        valuation,
        VALUATION_FILE,
    )

    # --------------------------------------------------------
    # 8. INTEGRAÇÃO 70 / 30
    # --------------------------------------------------------

    print(
        "[8/8] Integração "
        "fundamental 70/30..."
    )

    val_cols = [
        "CD_CVM",
        "VALUATION_SCORE",
    ]

    merged = (
        investability_approved
        .merge(
            valuation[val_cols],
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )
    )

    ticker_col = (
        "TICKER_LIQUIDEZ"
    )

    if (
        ticker_col
        not in merged.columns
    ):

        raise DataInsufficientError(
            "Investability live "
            "não retornou "
            "TICKER_LIQUIDEZ."
        )

    final = pd.DataFrame(
        {
            "TICKER":
                merged[
                    ticker_col
                ],

            "QUALITY_SCORE":
                merged[
                    "QUALITY_SCORE"
                ],

            "HISTORY_YEARS":
                merged[
                    "ANOS_NEGOCIACAO"
                ],

            "AVG_DAILY_LIQUIDITY_BRL":
                merged[
                    "LIQUIDEZ_MEDIA_DIARIA"
                ],

            "VALUATION_SCORE":
                merged[
                    "VALUATION_SCORE"
                ],
        }
    )

    final = (
        calculate_fundamental_score(
            final
        )
    )

    validate_live_output(
        final
    )

    final = (
        final
        .sort_values(
            "FUNDAMENTAL_SCORE",
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    return final


# ============================================================
# MANIFEST
# ============================================================

def build_manifest(
    status: str,
    error: str | None = None,
    rows: int | None = None,
) -> dict:

    return {

        "engine":
            "B3_INVESTMENT_ENGINE",

        "module":
            "build_live_fundamental_input",

        "methodology_version":
            METHODOLOGY_VERSION,

        "generated_at_utc":
            utc_now().isoformat(),

        "status":
            status,

        "error":
            error,

        "rows":
            rows,

        "methodology": {

            "quality_gate":
                QUALITY_GATE,

            "minimum_history_years":
                MIN_HISTORY_YEARS,

            "minimum_avg_daily_liquidity_brl":
                MIN_AVG_DAILY_LIQUIDITY_BRL,

            "quality_weight":
                QUALITY_WEIGHT,

            "valuation_weight":
                VALUATION_WEIGHT,

            "technical_changes_quality":
                False,

            "technical_rescues_failed_fundamental":
                False,

            "technical_participates_in_ranking":
                False,
        },

        "output_file":
            str(OUTPUT_FILE),
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    try:

        df = (
            build_live_fundamental_input()
        )

        write_csv_atomic(
            df,
            OUTPUT_FILE,
        )

        write_json_atomic(
            build_manifest(
                "OK",
                rows=len(df),
            ),
            OUTPUT_MANIFEST,
        )

        print(
            "\n"
            + "=" * 72
        )

        print(
            "LIVE FUNDAMENTAL CONCLUÍDO"
        )

        print(
            "Empresas:",
            len(df),
        )

        print(
            "Com valuation:",
            int(
                df[
                    "VALUATION_SCORE"
                ]
                .notna()
                .sum()
            ),
        )

        print(
            "Pendentes de valuation:",
            int(
                df[
                    "VALUATION_SCORE"
                ]
                .isna()
                .sum()
            ),
        )

        print(
            "Arquivo:",
            OUTPUT_FILE,
        )

        print(
            "=" * 72
        )

        return 0

    except DataInsufficientError as exc:

        write_json_atomic(
            build_manifest(
                "DATA_INSUFFICIENT",
                str(exc),
            ),
            OUTPUT_MANIFEST,
        )

        print(
            "\nDATA_INSUFFICIENT: "
            f"{exc}",
            file=sys.stderr,
        )

        return 3

    except MethodologyIntegrityError as exc:

        write_json_atomic(
            build_manifest(
                "METHODOLOGY_INTEGRITY_ERROR",
                str(exc),
            ),
            OUTPUT_MANIFEST,
        )

        print(
            "\nMETHODOLOGY_INTEGRITY_ERROR: "
            f"{exc}",
            file=sys.stderr,
        )

        return 4

    except Exception as exc:

        write_json_atomic(
            build_manifest(
                "ERROR",
                repr(exc),
            ),
            OUTPUT_MANIFEST,
        )

        print(
            "\nERROR: "
            f"{exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
