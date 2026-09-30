"""
B3 INVESTMENT ENGINE
BUILD LIVE VALUATION BASE — V1

Constrói:
data/live/fundamental/valuation_base_live.csv

Preserva a metodologia congelada do estudo:
- preço: B3
- quantidade de ações:
    impliedSharesOutstanding
    fallback sharesOutstanding
- fundamentos: CVM
- market cap = preço B3 * quantidade de ações
- sem imputação artificial
- sem alteração do Valuation Engine V1
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CAMINHOS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"

FUNDAMENTAL_DIR = LIVE_DIR / "fundamental"
B3_DIR = LIVE_DIR / "b3"

FUNDAMENTAL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

# Produzidos pela cadeia LIVE
QUALITY_FILE = (
    FUNDAMENTAL_DIR /
    "quality_live.csv"
)

INVESTABILITY_APPROVED_FILE = (
    FUNDAMENTAL_DIR /
    "investability_approved_live.csv"
)

# Fundamental base LIVE.
# O construtor procura também alternativas conhecidas.
FUNDAMENTAL_BASE_CANDIDATES = [
    FUNDAMENTAL_DIR / "fundamental_base_live.csv",
    FUNDAMENTAL_DIR / "cvm_fundamental_base_live.csv",
    LIVE_DIR / "processed" / "fundamental_base_live.csv",
]

# Preços do SPRE normalizados pelo build_b3_market_history.py
SPRE_PRICE_FILE = (
    B3_DIR /
    "spre_prices_live.csv"
)

# Parâmetros históricos congelados usados SOMENTE
# para preservar a metodologia de commodities.
FROZEN_REFERENCE_CANDIDATES = [
    DATA_DIR / "cell33c_valuation_score_2026_final.csv",
    DATA_DIR / "cell34_fundamental_ranking_2026.csv",
    DATA_DIR / "cell33b_valuation_score_2026_corrected.csv",
    DATA_DIR / "valuation_reference_frozen.csv",
]

OUTPUT_FILE = (
    FUNDAMENTAL_DIR /
    "valuation_base_live.csv"
)

DETAIL_FILE = (
    FUNDAMENTAL_DIR /
    "valuation_base_live_detail.csv"
)

MANIFEST_FILE = (
    FUNDAMENTAL_DIR /
    "valuation_base_live_manifest.json"
)

METHODOLOGY_VERSION = "B3_VALUATION_V1"


# ============================================================
# EXCEÇÕES
# ============================================================

class LiveValuationError(RuntimeError):
    pass


class DataInsufficientError(LiveValuationError):
    pass


class IntegrityError(LiveValuationError):
    pass


# ============================================================
# UTILITÁRIOS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def write_csv_atomic(
    df: pd.DataFrame,
    path: Path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    df.to_csv(
        tmp,
        index=False,
        encoding="utf-8-sig",
    )

    tmp.replace(path)


def write_json_atomic(
    data: dict,
    path: Path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def find_column(
    df: pd.DataFrame,
    candidates,
):
    mapping = {
        str(c).strip().upper(): c
        for c in df.columns
    }

    for candidate in candidates:
        key = str(
            candidate
        ).strip().upper()

        if key in mapping:
            return mapping[key]

    return None


def numeric(
    series,
):
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def normalize_ticker(
    value,
):
    if pd.isna(value):
        return np.nan

    value = (
        str(value)
        .strip()
        .upper()
        .replace(".SA", "")
    )

    if not value:
        return np.nan

    return value


# ============================================================
# LOCALIZAR FUNDAMENTAL BASE
# ============================================================

def locate_fundamental_base():
    for path in FUNDAMENTAL_BASE_CANDIDATES:
        if path.exists():
            return path

    # fallback controlado:
    # procura somente dentro de data/live
    candidates = []

    if LIVE_DIR.exists():
        candidates.extend(
            LIVE_DIR.rglob(
                "*fundamental*base*.csv"
            )
        )

    candidates = [
        p
        for p in candidates
        if (
            "valuation" not in
            p.name.lower()
        )
    ]

    if len(candidates) == 1:
        return candidates[0]

    raise DataInsufficientError(
        "Fundamental base LIVE não encontrada."
    )


# ============================================================
# CARREGAR INVESTABILITY
# ============================================================

def load_investability():
    if not INVESTABILITY_APPROVED_FILE.exists():
        raise DataInsufficientError(
            "investability_approved_live.csv "
            "não encontrado."
        )

    df = pd.read_csv(
        INVESTABILITY_APPROVED_FILE,
        low_memory=False,
    )

    if "CD_CVM" not in df.columns:
        raise DataInsufficientError(
            "Investability sem CD_CVM."
        )

    ticker_col = find_column(
        df,
        [
            "TICKER_LIQUIDEZ",
            "TICKER",
            "TICKER_VALUATION",
        ],
    )

    if ticker_col is None:
        raise DataInsufficientError(
            "Investability sem ticker."
        )

    df["CD_CVM"] = numeric(
        df["CD_CVM"]
    ).astype("Int64")

    df["TICKER_VALUATION"] = (
        df[ticker_col]
        .apply(normalize_ticker)
    )

    df = (
        df
        .dropna(
            subset=[
                "CD_CVM",
                "TICKER_VALUATION",
            ]
        )
        .drop_duplicates(
            subset=["CD_CVM"]
        )
        .copy()
    )

    return df


# ============================================================
# CARREGAR QUALITY
# ============================================================

def load_quality():
    if not QUALITY_FILE.exists():
        raise DataInsufficientError(
            "quality_live.csv não encontrado."
        )

    df = pd.read_csv(
        QUALITY_FILE,
        low_memory=False,
    )

    required = {
        "CD_CVM",
        "QUALITY_SCORE",
    }

    missing = (
        required -
        set(df.columns)
    )

    if missing:
        raise DataInsufficientError(
            "Quality sem colunas: "
            + ", ".join(
                sorted(missing)
            )
        )

    df["CD_CVM"] = numeric(
        df["CD_CVM"]
    ).astype("Int64")

    df["QUALITY_SCORE"] = numeric(
        df["QUALITY_SCORE"]
    )

    return (
        df[
            [
                "CD_CVM",
                "QUALITY_SCORE",
            ]
        ]
        .drop_duplicates(
            subset=["CD_CVM"]
        )
    )


# ============================================================
# CARREGAR FUNDAMENTOS CVM
# ============================================================

def load_fundamental_base():
    path = locate_fundamental_base()

    print(
        "Fundamental base:",
        path,
    )

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    cd_col = find_column(
        df,
        [
            "CD_CVM",
            "COD_CVM",
        ],
    )

    year_col = find_column(
        df,
        [
            "ANO",
            "EXERCICIO",
            "YEAR",
        ],
    )

    if cd_col is None:
        raise DataInsufficientError(
            "Fundamental base sem CD_CVM."
        )

    df["CD_CVM"] = numeric(
        df[cd_col]
    ).astype("Int64")

    if year_col is not None:
        df["_ANO"] = numeric(
            df[year_col]
        )

        # ----------------------------------------------------
        # Seleciona o exercício fundamental MAIS RECENTE
        # que realmente possui dados contábeis utilizáveis.
        #
        # A grade LIVE pode conter o ano corrente antes de a
        # DFP anual desse exercício estar completa. Portanto,
        # não podemos simplesmente usar o maior ANO.
        #
        # Regra preservada do estudo:
        # - financeiros: PL + lucro disponíveis;
        # - não financeiros: PL + lucro + EBIT disponíveis.
        #
        # Não há ano hardcoded: quando o exercício novo estiver
        # completo, ele passa a ser escolhido automaticamente.
        # ----------------------------------------------------

        pl_col = find_column(
            df,
            [
                "PATRIMONIO_LIQUIDO",
                "PATRIMONIO_LIQUIDO_R",
                "PL_VAL",
                "PL_VAL_BRL",
            ],
        )

        lucro_col = find_column(
            df,
            [
                "LUCRO_LIQUIDO",
                "LUCRO_LIQUIDO_R",
                "LUCRO_VAL",
                "LUCRO_VAL_BRL",
            ],
        )

        ebit_col = find_column(
            df,
            [
                "EBIT",
                "EBIT_R",
                "EBIT_VAL",
                "EBIT_VAL_BRL",
            ],
        )

        motor_col = find_column(
            df,
            [
                "MOTOR_FINAL",
            ],
        )

        if pl_col is None or lucro_col is None:
            raise DataInsufficientError(
                "Fundamental base sem PL e/ou lucro "
                "para selecionar exercício válido."
            )

        pl_ok = numeric(df[pl_col]).notna()
        lucro_ok = numeric(df[lucro_col]).notna()

        if motor_col is not None:
            motor = (
                df[motor_col]
                .astype("string")
                .str.strip()
                .str.upper()
            )

            financeiro = motor.isin(
                {
                    "FINANCEIRO_BANCO",
                    "FINANCEIRO_SEGUROS",
                    "FINANCEIRO_ESPECIAL",
                }
            )
        else:
            financeiro = pd.Series(
                False,
                index=df.index,
            )

        if ebit_col is not None:
            ebit_ok = numeric(df[ebit_col]).notna()
        else:
            ebit_ok = pd.Series(
                False,
                index=df.index,
            )

        df["_FUNDAMENTOS_VALUATION_OK"] = (
            pl_ok
            &
            lucro_ok
            &
            (
                financeiro
                |
                ebit_ok
            )
        )

        validos = df[
            df["_FUNDAMENTOS_VALUATION_OK"]
            &
            df["_ANO"].notna()
        ].copy()

        if validos.empty:
            raise DataInsufficientError(
                "Nenhum exercício com fundamentos "
                "suficientes para valuation."
            )

        selecionados = (
            validos
            .sort_values(
                [
                    "CD_CVM",
                    "_ANO",
                ]
            )
            .groupby(
                "CD_CVM",
                as_index=False,
            )
            .tail(1)
            .copy()
        )

        # Fail-safe: preserva empresas sem linha completa para
        # que permaneçam pendentes, sem inventar fundamentos.
        cds_selecionados = set(
            selecionados["CD_CVM"]
            .dropna()
            .tolist()
        )

        faltantes = df[
            ~df["CD_CVM"].isin(cds_selecionados)
        ].copy()

        if not faltantes.empty:
            faltantes = (
                faltantes
                .sort_values(
                    [
                        "CD_CVM",
                        "_ANO",
                    ]
                )
                .groupby(
                    "CD_CVM",
                    as_index=False,
                )
                .tail(1)
                .copy()
            )

            selecionados = pd.concat(
                [
                    selecionados,
                    faltantes,
                ],
                ignore_index=True,
            )

        df = selecionados.copy()

        anos_validos = (
            df.loc[
                df["_FUNDAMENTOS_VALUATION_OK"],
                "_ANO",
            ]
            .dropna()
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )

        print(
            "Exercícios fundamentais selecionados:",
            anos_validos,
        )
    else:
        if df["CD_CVM"].duplicated().any():
            raise IntegrityError(
                "Fundamental base possui "
                "CD_CVM duplicado e não há "
                "coluna ANO para selecionar "
                "o exercício mais recente."
            )

    return df


# ============================================================
# COLUNAS FUNDAMENTAIS
# ============================================================

def extract_fundamentals(
    df: pd.DataFrame,
):
    mapping = {
        "PATRIMONIO_LIQUIDO_R": [
            "PATRIMONIO_LIQUIDO",
            "PATRIMONIO_LIQUIDO_R",
            "PL_VAL",
            "PL_VAL_BRL",
        ],

        "LUCRO_LIQUIDO_R": [
            "LUCRO_LIQUIDO",
            "LUCRO_LIQUIDO_R",
            "LUCRO_VAL",
            "LUCRO_VAL_BRL",
        ],

        "EBIT_R": [
            "EBIT",
            "EBIT_R",
            "EBIT_VAL",
            "EBIT_VAL_BRL",
        ],

        "DIVIDA_LIQUIDA_R": [
            "DIVIDA_LIQUIDA",
            "DIVIDA_LIQUIDA_R",
            "DIVIDA_LIQUIDA_VAL",
            "DIVIDA_LIQUIDA_VAL_BRL",
        ],

        "MOTOR_FINAL": [
            "MOTOR_FINAL",
        ],

        "FAMILIA_VALUATION": [
            "FAMILIA_VALUATION",
        ],

        "DENOM_CIA_ATUAL": [
            "DENOM_CIA_ATUAL",
            "DENOM_CIA",
            "DENOM_SOCIAL",
        ],
    }

    out = pd.DataFrame()

    out["CD_CVM"] = df["CD_CVM"]

    for target, candidates in mapping.items():
        col = find_column(
            df,
            candidates,
        )

        if col is None:
            out[target] = np.nan
        else:
            out[target] = df[col]

    # --------------------------------------------------------
    # A base CVM validada trabalha em R$ mil.
    #
    # Se a coluna de origem já era explicitamente *_BRL,
    # não multiplica novamente.
    # --------------------------------------------------------

    monetary_targets = [
        "PATRIMONIO_LIQUIDO_R",
        "LUCRO_LIQUIDO_R",
        "EBIT_R",
        "DIVIDA_LIQUIDA_R",
    ]

    for target in monetary_targets:
        candidates = mapping[target]

        source = find_column(
            df,
            candidates,
        )

        values = numeric(
            out[target]
        )

        if (
            source is not None
            and str(source)
            .upper()
            .endswith("_BRL")
        ):
            out[target] = values

        else:
            out[target] = (
                values * 1000.0
            )

    return out


# ============================================================
# FAMÍLIA DE VALUATION
# ============================================================

def derive_family(
    df: pd.DataFrame,
):
    out = df.copy()

    family = (
        out["FAMILIA_VALUATION"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    motor = (
        out["MOTOR_FINAL"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    # Mapeamento congelado do estudo.
    motor_to_family = {
        "COMMODITY": "COMMODITY",
        "OPERACIONAL": "OPERACIONAL",
        "UTILITY": "UTILITY",
        "FINANCEIRO_BANCO": "FINANCEIRO",
        "FINANCEIRO_SEGUROS": "FINANCEIRO",
        "FINANCEIRO_ESPECIAL": "FINANCEIRO",
    }

    family_from_motor = motor.map(
        motor_to_family
    )

    # MOTOR_FINAL é prioritário quando possui mapeamento
    # conhecido. Caso contrário, preserva uma família válida
    # já existente.
    family = family_from_motor.combine_first(
        family
    )

    valid = {
        "COMMODITY",
        "OPERACIONAL",
        "UTILITY",
        "FINANCEIRO",
    }

    family = family.where(
        family.isin(valid)
    )

    out[
        "FAMILIA_VALUATION"
    ] = family

    return out


# ============================================================
# PREÇO B3 SPRE
# ============================================================

def load_b3_prices():
    if not SPRE_PRICE_FILE.exists():
        raise DataInsufficientError(
            "spre_prices_live.csv "
            "não encontrado."
        )

    df = pd.read_csv(
        SPRE_PRICE_FILE,
        low_memory=False,
    )

    ticker_col = find_column(
        df,
        [
            "TICKER",
            "TCKRSYMB",
            "TICKER_VALUATION",
        ],
    )

    date_col = find_column(
        df,
        [
            "DATA",
            "TRADDT",
            "DATE",
        ],
    )

    price_col = find_column(
        df,
        [
            "LASTPRIC",
            "LAST_PRICE",
            "PRECO_FECHAMENTO",
            "PRECO",
            "CLOSE",
        ],
    )

    if (
        ticker_col is None
        or date_col is None
        or price_col is None
    ):
        raise DataInsufficientError(
            "SPRE normalizado sem "
            "ticker/data/preço."
        )

    out = pd.DataFrame()

    out["TICKER_VALUATION"] = (
        df[ticker_col]
        .apply(normalize_ticker)
    )

    out["DATA_B3"] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    out["PRECO_B3"] = numeric(
        df[price_col]
    )

    out = out[
        out["PRECO_B3"].gt(0)
    ].copy()

    out = out.dropna(
        subset=[
            "TICKER_VALUATION",
            "DATA_B3",
        ]
    )

    # Seleciona a cotação mais recente
    # de cada ticker.
    out = (
        out
        .sort_values(
            [
                "TICKER_VALUATION",
                "DATA_B3",
            ]
        )
        .groupby(
            "TICKER_VALUATION",
            as_index=False,
        )
        .tail(1)
        .copy()
    )

    return out


# ============================================================
# YAHOO — QUANTIDADE DE AÇÕES
# ============================================================

def get_share_structure(
    ticker: str,
):
    symbol = (
        f"{ticker}.SA"
    )

    result = {
        "TICKER_VALUATION": ticker,
        "IMPLIED_SHARES_YF": np.nan,
        "SHARES_OUTSTANDING_YF": np.nan,
        "MARKET_CAP_YF": np.nan,
        "MOEDA_YF": None,
        "PRECO_YF_ATUAL": np.nan,
    }

    try:
        tk = yf.Ticker(symbol)

        try:
            fast = tk.fast_info

            if fast is not None:
                try:
                    result[
                        "MARKET_CAP_YF"
                    ] = fast.get(
                        "market_cap",
                        np.nan,
                    )
                except Exception:
                    pass

                try:
                    result[
                        "PRECO_YF_ATUAL"
                    ] = fast.get(
                        "last_price",
                        np.nan,
                    )
                except Exception:
                    pass

                try:
                    result[
                        "MOEDA_YF"
                    ] = fast.get(
                        "currency",
                        None,
                    )
                except Exception:
                    pass

        except Exception:
            pass

        try:
            info = tk.info or {}

            result[
                "IMPLIED_SHARES_YF"
            ] = info.get(
                "impliedSharesOutstanding",
                np.nan,
            )

            result[
                "SHARES_OUTSTANDING_YF"
            ] = info.get(
                "sharesOutstanding",
                np.nan,
            )

            if pd.isna(
                result["MARKET_CAP_YF"]
            ):
                result[
                    "MARKET_CAP_YF"
                ] = info.get(
                    "marketCap",
                    np.nan,
                )

            if not result[
                "MOEDA_YF"
            ]:
                result[
                    "MOEDA_YF"
                ] = info.get(
                    "currency",
                    None,
                )

            if pd.isna(
                result[
                    "PRECO_YF_ATUAL"
                ]
            ):
                result[
                    "PRECO_YF_ATUAL"
                ] = info.get(
                    "currentPrice",
                    np.nan,
                )

        except Exception:
            pass

    except Exception:
        pass

    return result


def build_share_structure(
    tickers,
):
    rows = []

    tickers = sorted(
        set(
            t
            for t in tickers
            if pd.notna(t)
        )
    )

    total = len(tickers)

    for i, ticker in enumerate(
        tickers,
        start=1,
    ):
        result = get_share_structure(
            ticker
        )

        implied = pd.to_numeric(
            result[
                "IMPLIED_SHARES_YF"
            ],
            errors="coerce",
        )

        outstanding = pd.to_numeric(
            result[
                "SHARES_OUTSTANDING_YF"
            ],
            errors="coerce",
        )

        status = (
            "OK"
            if (
                pd.notna(implied)
                or pd.notna(outstanding)
            )
            else "SEM AÇÕES"
        )

        print(
            f"[{i}/{total}] "
            f"{ticker:<10} "
            f"{status}"
        )

        rows.append(result)

        time.sleep(0.15)

    return pd.DataFrame(rows)


# ============================================================
# REFERÊNCIA HISTÓRICA CONGELADA
# ============================================================

def locate_frozen_reference():
    for path in FROZEN_REFERENCE_CANDIDATES:
        if path.exists():
            return path

    return None


def load_frozen_reference():
    path = locate_frozen_reference()

    columns = [
        "CD_CVM",
        "PL_NORMALIZADO_C25",
        "EV_EBIT_NORMALIZADO_C25_CORRETO",
        "MARKET_CAP_ANTIGO_CORRETO",
        "ROE_HISTORICO_VALUATION",
    ]

    if path is None:
        print(
            "Referência histórica commodity: "
            "não encontrada no repositório."
        )

        return pd.DataFrame(
            columns=columns
        )

    print(
        "Referência congelada:",
        path,
    )

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    if "CD_CVM" not in df.columns:
        raise IntegrityError(
            "Referência congelada "
            "sem CD_CVM."
        )

    out = pd.DataFrame()

    out["CD_CVM"] = numeric(
        df["CD_CVM"]
    ).astype("Int64")

    for col in columns[1:]:
        if col in df.columns:
            out[col] = numeric(
                df[col]
            )
        else:
            out[col] = np.nan

    return (
        out
        .drop_duplicates(
            subset=["CD_CVM"]
        )
    )


# ============================================================
# CONSTRUIR BASE
# ============================================================

def build_live_valuation_base():
    print("=" * 78)
    print(
        "B3 INVESTMENT ENGINE — "
        "BUILD LIVE VALUATION BASE V1"
    )
    print("=" * 78)

    # --------------------------------------------------------
    # 1. UNIVERSO APROVADO
    # --------------------------------------------------------

    investability = (
        load_investability()
    )

    quality = load_quality()

    base = (
        investability[
            [
                "CD_CVM",
                "TICKER_VALUATION",
            ]
        ]
        .merge(
            quality,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )
    )

    print(
        "Universo Investability:",
        len(base),
    )

    # --------------------------------------------------------
    # 2. FUNDAMENTOS CVM
    # --------------------------------------------------------

    fundamental_raw = (
        load_fundamental_base()
    )

    fundamentals = (
        extract_fundamentals(
            fundamental_raw
        )
    )

    base = base.merge(
        fundamentals,
        on="CD_CVM",
        how="left",
        validate="one_to_one",
    )

    base = derive_family(
        base
    )

    # --------------------------------------------------------
    # 3. PREÇOS B3
    # --------------------------------------------------------

    prices = load_b3_prices()

    base = base.merge(
        prices,
        on="TICKER_VALUATION",
        how="left",
        validate="many_to_one",
    )

    # --------------------------------------------------------
    # 4. QUANTIDADE DE AÇÕES
    # --------------------------------------------------------

    shares = build_share_structure(
        base[
            "TICKER_VALUATION"
        ].dropna()
    )

    base = base.merge(
        shares,
        on="TICKER_VALUATION",
        how="left",
        validate="many_to_one",
    )

    # Regra congelada:
    # impliedSharesOutstanding
    # fallback sharesOutstanding

    base[
        "ACOES_REFERENCIA"
    ] = numeric(
        base[
            "IMPLIED_SHARES_YF"
        ]
    ).combine_first(
        numeric(
            base[
                "SHARES_OUTSTANDING_YF"
            ]
        )
    )

    base[
        "ACOES_OK"
    ] = (
        base[
            "ACOES_REFERENCIA"
        ]
        .notna()
        &
        base[
            "ACOES_REFERENCIA"
        ]
        .gt(0)
    )

    # --------------------------------------------------------
    # 5. MARKET CAP
    # --------------------------------------------------------

    base[
        "MARKET_CAP_ATUAL"
    ] = np.where(
        (
            base["PRECO_B3"].gt(0)
            &
            base["ACOES_OK"]
        ),
        (
            base["PRECO_B3"]
            *
            base["ACOES_REFERENCIA"]
        ),
        np.nan,
    )

    base[
        "MARKET_CAP_OK"
    ] = (
        numeric(
            base[
                "MARKET_CAP_ATUAL"
            ]
        )
        .gt(0)
    )

    # --------------------------------------------------------
    # 6. P/L
    # --------------------------------------------------------

    base[
        "PL_ATUAL"
    ] = np.where(
        (
            base["MARKET_CAP_OK"]
            &
            base[
                "LUCRO_LIQUIDO_R"
            ].gt(0)
        ),
        (
            base[
                "MARKET_CAP_ATUAL"
            ]
            /
            base[
                "LUCRO_LIQUIDO_R"
            ]
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # 7. P/VP
    # --------------------------------------------------------

    base[
        "P_VP_ATUAL"
    ] = np.where(
        (
            base["MARKET_CAP_OK"]
            &
            base[
                "PATRIMONIO_LIQUIDO_R"
            ].gt(0)
        ),
        (
            base[
                "MARKET_CAP_ATUAL"
            ]
            /
            base[
                "PATRIMONIO_LIQUIDO_R"
            ]
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # 8. EV
    # --------------------------------------------------------

    base[
        "EV_ATUAL"
    ] = np.where(
        (
            base["MARKET_CAP_OK"]
            &
            base[
                "DIVIDA_LIQUIDA_R"
            ].notna()
        ),
        (
            base[
                "MARKET_CAP_ATUAL"
            ]
            +
            base[
                "DIVIDA_LIQUIDA_R"
            ]
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # 9. EV / EBIT
    # --------------------------------------------------------

    base[
        "EV_EBIT_ATUAL"
    ] = np.where(
        (
            base[
                "EV_ATUAL"
            ].notna()
            &
            base[
                "EBIT_R"
            ].gt(0)
        ),
        (
            base[
                "EV_ATUAL"
            ]
            /
            base[
                "EBIT_R"
            ]
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # 10. ROE ATUAL
    # --------------------------------------------------------

    base[
        "ROE_ATUAL"
    ] = np.where(
        base[
            "PATRIMONIO_LIQUIDO_R"
        ].gt(0),
        (
            base[
                "LUCRO_LIQUIDO_R"
            ]
            /
            base[
                "PATRIMONIO_LIQUIDO_R"
            ]
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # 11. REFERÊNCIA HISTÓRICA CONGELADA
    # --------------------------------------------------------

    frozen = load_frozen_reference()

    if not frozen.empty:
        base = base.merge(
            frozen,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )

    else:
        for col in [
            "PL_NORMALIZADO_C25",
            "EV_EBIT_NORMALIZADO_C25_CORRETO",
            "MARKET_CAP_ANTIGO_CORRETO",
            "ROE_HISTORICO_VALUATION",
        ]:
            base[col] = np.nan

    # Para financeiros, se o histórico
    # congelado estiver disponível,
    # ele permanece prioritário.
    #
    # Não criamos histórico artificial.

    # --------------------------------------------------------
    # 12. STATUS
    # --------------------------------------------------------

    base[
        "STATUS_VALUATION_BASE"
    ] = "OK"

    base.loc[
        base[
            "FAMILIA_VALUATION"
        ].isna(),
        "STATUS_VALUATION_BASE",
    ] = "PENDENTE_FAMILIA"

    base.loc[
        base[
            "PRECO_B3"
        ].isna(),
        "STATUS_VALUATION_BASE",
    ] = "PENDENTE_PRECO_B3"

    base.loc[
        ~base[
            "ACOES_OK"
        ],
        "STATUS_VALUATION_BASE",
    ] = "PENDENTE_ACOES"

    base.loc[
        ~base[
            "MARKET_CAP_OK"
        ],
        "STATUS_VALUATION_BASE",
    ] = "PENDENTE_MARKET_CAP"

    # --------------------------------------------------------
    # 13. SAÍDA EXATA DO VALUATION ENGINE
    # --------------------------------------------------------

    required_output = [
        "CD_CVM",
        "TICKER_VALUATION",
        "QUALITY_SCORE",
        "FAMILIA_VALUATION",
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

    for col in required_output:
        if col not in base.columns:
            base[col] = np.nan

    valuation_base = (
        base[
            required_output
        ]
        .copy()
    )

    # --------------------------------------------------------
    # 14. INTEGRIDADE
    # --------------------------------------------------------

    if valuation_base[
        "CD_CVM"
    ].duplicated().any():
        raise IntegrityError(
            "CD_CVM duplicado na "
            "valuation_base_live."
        )

    if len(
        valuation_base
    ) != len(
        investability
    ):
        raise IntegrityError(
            "Universo alterado durante "
            "construção do Valuation LIVE."
        )

    # --------------------------------------------------------
    # 15. SALVAR
    # --------------------------------------------------------

    write_csv_atomic(
        valuation_base,
        OUTPUT_FILE,
    )

    write_csv_atomic(
        base,
        DETAIL_FILE,
    )

    latest_b3 = (
        pd.to_datetime(
            base["DATA_B3"],
            errors="coerce",
        )
        .max()
    )

    status_counts = (
        base[
            "STATUS_VALUATION_BASE"
        ]
        .value_counts(
            dropna=False
        )
        .to_dict()
    )

    manifest = {
        "engine":
            "B3_INVESTMENT_ENGINE",

        "module":
            "build_live_valuation_base",

        "methodology_version":
            METHODOLOGY_VERSION,

        "generated_at_utc":
            utc_now().isoformat(),

        "status":
            "OK",

        "universe":
            int(
                len(
                    valuation_base
                )
            ),

        "latest_b3_date":
            (
                latest_b3.isoformat()
                if pd.notna(
                    latest_b3
                )
                else None
            ),

        "market_cap_available":
            int(
                valuation_base[
                    "MARKET_CAP_ATUAL"
                ]
                .notna()
                .sum()
            ),

        "pl_available":
            int(
                valuation_base[
                    "PL_ATUAL"
                ]
                .notna()
                .sum()
            ),

        "pvp_available":
            int(
                valuation_base[
                    "P_VP_ATUAL"
                ]
                .notna()
                .sum()
            ),

        "ev_ebit_available":
            int(
                valuation_base[
                    "EV_EBIT_ATUAL"
                ]
                .notna()
                .sum()
            ),

        "status_counts":
            status_counts,

        "methodology": {
            "price_source":
                "B3",

            "shares_preference":
                "impliedSharesOutstanding",

            "shares_fallback":
                "sharesOutstanding",

            "market_cap_formula":
                "B3_PRICE_X_REFERENCE_SHARES",

            "fundamentals_source":
                "CVM",

            "artificial_imputation":
                False,

            "valuation_engine_changed":
                False,
        },

        "output_file":
            str(
                OUTPUT_FILE
            ),
    }

    write_json_atomic(
        manifest,
        MANIFEST_FILE,
    )

    # --------------------------------------------------------
    # 16. RESULTADO
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("VALUATION BASE LIVE CONCLUÍDA")
    print("=" * 78)

    print(
        "Universo:",
        len(
            valuation_base
        ),
    )

    print(
        "Market Cap:",
        int(
            valuation_base[
                "MARKET_CAP_ATUAL"
            ]
            .notna()
            .sum()
        ),
    )

    print(
        "P/L:",
        int(
            valuation_base[
                "PL_ATUAL"
            ]
            .notna()
            .sum()
        ),
    )

    print(
        "P/VP:",
        int(
            valuation_base[
                "P_VP_ATUAL"
            ]
            .notna()
            .sum()
        ),
    )

    print(
        "EV/EBIT:",
        int(
            valuation_base[
                "EV_EBIT_ATUAL"
            ]
            .notna()
            .sum()
        ),
    )

    print()
    print(
        "Arquivo:",
        OUTPUT_FILE,
    )

    print("=" * 78)

    return valuation_base


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        build_live_valuation_base()
        return 0

    except Exception as exc:
        manifest = {
            "engine":
                "B3_INVESTMENT_ENGINE",

            "module":
                "build_live_valuation_base",

            "methodology_version":
                METHODOLOGY_VERSION,

            "generated_at_utc":
                utc_now().isoformat(),

            "status":
                "DATA_INSUFFICIENT",

            "error":
                str(exc),
        }

        write_json_atomic(
            manifest,
            MANIFEST_FILE,
        )

        print()
        print(
            "ERRO:",
            exc,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
