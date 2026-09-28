"""
B3 INVESTMENT ENGINE
BUILD B3 MARKET HISTORY — V1

Objetivo
--------
Construir a base oficial normalizada de negociação utilizada pelo
B3 Investability Engine.

Fontes:
1. COTAHIST anual oficial B3 — histórico encerrado;
2. BVBG.186.01 / Simplified Price Report — ano corrente.

Saída:
data/live/b3/market_history_live.csv

Colunas mínimas:
TICKER
DATA
VOLTOT

IMPORTANTE
----------
Este módulo NÃO altera metodologia.

Ele NÃO:
- calcula Quality Score;
- calcula Valuation;
- altera o limite de 10 anos;
- altera o limite de R$ 6 milhões;
- cria Technical Score;
- cria ranking;
- substitui o Investability Engine.

Sua única função é normalizar os dados oficiais B3.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
B3_DIR = LIVE_DIR / "b3"

HISTORICAL_DIR = (
    B3_DIR / "cotahist"
)

CURRENT_YEAR_DIR = (
    B3_DIR / "current_year"
)

OUTPUT_FILE = (
    B3_DIR / "market_history_live.csv"
)

MANIFEST_FILE = (
    B3_DIR / "market_history_manifest.json"
)

B3_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CONSTANTS
# ============================================================

CURRENT_YEAR = datetime.now(
    timezone.utc
).year

COTAHIST_PREFIX = "COTAHIST_A"

SPRE_PREFIX = "SPRE"

VALID_MARKET_TYPE = "010"

METHODOLOGY_VERSION = (
    "B3_MARKET_HISTORY_V1"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class B3MarketHistoryError(
    RuntimeError
):
    pass


class DataInsufficientError(
    B3MarketHistoryError
):
    pass


# ============================================================
# UTILITIES
# ============================================================

def utc_now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


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


def normalize_ticker(
    value,
):

    if pd.isna(value):
        return None

    value = (
        str(value)
        .strip()
        .upper()
    )

    if not value:
        return None

    return value


# ============================================================
# COTAHIST — FIXED WIDTH
# ============================================================

def parse_cotahist_line(
    line: str,
):

    """
    Layout necessário da série histórica B3.

    Campos utilizados:

    TIPREG:
        posição 01-02

    DATA:
        posição 03-10

    CODNEG:
        posição 13-24

    TPMERC:
        posição 25-27

    VOLTOT:
        posição 171-188
        duas casas decimais implícitas.

    Mantemos apenas:
    TIPREG = 01
    TPMERC = 010
    """

    if len(line) < 188:
        return None

    tipreg = line[
        0:2
    ]

    if tipreg != "01":
        return None

    data_raw = line[
        2:10
    ]

    ticker = (
        line[
            12:24
        ]
        .strip()
        .upper()
    )

    tpmerc = line[
        24:27
    ]

    if tpmerc != VALID_MARKET_TYPE:
        return None

    voltot_raw = line[
        170:188
    ]

    try:

        data = pd.to_datetime(
            data_raw,
            format="%Y%m%d",
            errors="raise",
        )

        voltot = (
            int(voltot_raw)
            / 100.0
        )

    except Exception:

        return None

    if not ticker:
        return None

    return {
        "TICKER":
            ticker,

        "DATA":
            data,

        "VOLTOT":
            float(voltot),

        "SOURCE":
            "COTAHIST",
    }


def parse_cotahist_zip(
    path: Path,
) -> pd.DataFrame:

    rows = []

    try:

        with zipfile.ZipFile(
            path,
            "r",
        ) as archive:

            names = archive.namelist()

            if not names:

                raise DataInsufficientError(
                    f"ZIP vazio: {path}"
                )

            data_name = names[0]

            with archive.open(
                data_name,
                "r",
            ) as file:

                for raw in file:

                    try:

                        line = raw.decode(
                            "latin-1"
                        )

                    except Exception:

                        continue

                    parsed = (
                        parse_cotahist_line(
                            line
                        )
                    )

                    if parsed is not None:

                        rows.append(
                            parsed
                        )

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            f"COTAHIST inválido: {path}"
        ) from exc

    return pd.DataFrame(
        rows
    )


# ============================================================
# COTAHIST — HISTÓRICO
# ============================================================

def load_historical_cotahist():

    if not HISTORICAL_DIR.exists():

        raise DataInsufficientError(
            "Diretório histórico B3 "
            "não encontrado: "
            f"{HISTORICAL_DIR}"
        )

    files = sorted(
        HISTORICAL_DIR.glob(
            "COTAHIST_A*.ZIP"
        )
    )

    if not files:

        files = sorted(
            HISTORICAL_DIR.glob(
                "COTAHIST_A*.zip"
            )
        )

    if not files:

        raise DataInsufficientError(
            "Nenhum COTAHIST anual "
            "foi encontrado."
        )

    frames = []

    years_loaded = []

    for path in files:

        match = re.search(
            r"COTAHIST_A(\d{4})",
            path.name.upper(),
        )

        if not match:
            continue

        year = int(
            match.group(1)
        )

        # Ano corrente é tratado pela
        # camada diária BVBG.186.01.
        if year >= CURRENT_YEAR:
            continue

        print(
            f"  COTAHIST {year}: "
            f"{path.name}"
        )

        df = parse_cotahist_zip(
            path
        )

        if df.empty:

            raise DataInsufficientError(
                "COTAHIST sem registros "
                f"válidos: {path}"
            )

        frames.append(
            df
        )

        years_loaded.append(
            year
        )

    if not frames:

        raise DataInsufficientError(
            "Nenhum histórico COTAHIST "
            "válido foi carregado."
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    return (
        result,
        sorted(
            set(years_loaded)
        ),
    )


# ============================================================
# SPRE — HELPERS
# ============================================================

def _read_zip_payload(
    path: Path,
) -> bytes:

    try:

        with zipfile.ZipFile(
            path,
            "r",
        ) as archive:

            names = [
                name
                for name
                in archive.namelist()
                if not name.endswith("/")
            ]

            if not names:

                raise DataInsufficientError(
                    f"SPRE vazio: {path}"
                )

            return archive.read(
                names[0]
            )

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            f"SPRE inválido: {path}"
        ) from exc


def _decode_text(
    payload: bytes,
) -> str:

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "latin-1",
    ):

        try:

            return payload.decode(
                encoding
            )

        except UnicodeDecodeError:
            pass

    raise DataInsufficientError(
        "Não foi possível decodificar "
        "arquivo SPRE."
    )


def _read_delimited_text(
    text: str,
) -> pd.DataFrame:

    candidates = [
        ";",
        ",",
        "\t",
        "|",
    ]

    best = None

    for separator in candidates:

        try:

            df = pd.read_csv(
                io.StringIO(text),
                sep=separator,
                low_memory=False,
            )

        except Exception:
            continue

        if (
            best is None
            or len(df.columns)
            >
            len(best.columns)
        ):

            best = df

    if (
        best is None
        or len(best.columns) <= 1
    ):

        raise DataInsufficientError(
            "Layout SPRE não reconhecido."
        )

    return best


def _normalize_column_name(
    value,
) -> str:

    value = (
        str(value)
        .strip()
        .upper()
    )

    value = (
        value
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(".", "_")
    )

    while "__" in value:
        value = value.replace(
            "__",
            "_",
        )

    return value


def _find_column(
    columns,
    candidates,
):

    normalized = {
        _normalize_column_name(
            column
        ):
        column

        for column
        in columns
    }

    for candidate in candidates:

        key = (
            _normalize_column_name(
                candidate
            )
        )

        if key in normalized:

            return normalized[
                key
            ]

    return None


# ============================================================
# SPRE — NORMALIZAÇÃO
# ============================================================

def normalize_spre_dataframe(
    df: pd.DataFrame,
    trade_date: pd.Timestamp,
) -> pd.DataFrame:

    """
    O layout BVBG.186.01 pode sofrer alterações de nomes de
    cabeçalho ao longo do tempo.

    Este parser NÃO inventa valores. Ele somente aceita campos
    identificados explicitamente.

    Para Investability precisamos:
    - ticker;
    - data;
    - volume financeiro negociado.

    Caso a B3 não forneça campo compatível, o processo falha
    como DATA_INSUFFICIENT.
    """

    ticker_col = _find_column(
        df.columns,
        [
            "TICKER",
            "TCKRSYMB",
            "TCKR_SYMB",
            "CODNEG",
            "CODIGO_NEGOCIACAO",
            "SECURITY_SYMBOL",
        ],
    )

    volume_col = _find_column(
        df.columns,
        [
            "VOLTOT",
            "FINANCIAL_VOLUME",
            "FINANCIALVOLUME",
            "FINANCIAL_VOLUME_TRADED",
            "TRADFINVOL",
            "TRAD_FIN_VOL",
            "TRADFINVOLUME",
            "TRAD_FIN_VOLUME",
            "TOTFINVOL",
            "TOT_FIN_VOL",
            "VOLUME_FINANCEIRO",
            "VOLUME_FINANCEIRO_NEGOCIADO",
        ],
    )

    if ticker_col is None:

        raise DataInsufficientError(
            "SPRE sem coluna de ticker "
            "reconhecida."
        )

    if volume_col is None:

        raise DataInsufficientError(
            "SPRE sem coluna de volume "
            "financeiro reconhecida."
        )

    out = pd.DataFrame()

    out["TICKER"] = (
        df[ticker_col]
        .map(normalize_ticker)
    )

    volume_raw = (
        df[volume_col]
        .astype(str)
        .str.strip()
    )

    # Tenta primeiro padrão numérico
    # internacional.
    volume = pd.to_numeric(
        volume_raw,
        errors="coerce",
    )

    # Se necessário, tenta padrão
    # brasileiro 1.234,56.
    missing = volume.isna()

    if missing.any():

        br = (
            volume_raw[
                missing
            ]
            .str.replace(
                ".",
                "",
                regex=False,
            )
            .str.replace(
                ",",
                ".",
                regex=False,
            )
        )

        volume.loc[
            missing
        ] = pd.to_numeric(
            br,
            errors="coerce",
        )

    out["VOLTOT"] = volume

    out["DATA"] = pd.Timestamp(
        trade_date
    ).normalize()

    out["SOURCE"] = (
        "BVBG.186.01"
    )

    out = out.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    out = out[
        out["VOLTOT"] >= 0
    ]

    return out


def parse_spre_zip(
    path: Path,
) -> pd.DataFrame:

    match = re.search(
        r"SPRE(\d{6})",
        path.name.upper(),
    )

    if not match:

        raise DataInsufficientError(
            "Nome SPRE incompatível: "
            f"{path.name}"
        )

    date_code = match.group(1)

    trade_date = pd.to_datetime(
        date_code,
        format="%y%m%d",
        errors="raise",
    )

    payload = _read_zip_payload(
        path
    )

    # Alguns downloads podem conter
    # outro ZIP internamente.
    if payload[:2] == b"PK":

        try:

            with zipfile.ZipFile(
                io.BytesIO(payload),
                "r",
            ) as nested:

                names = [
                    name
                    for name
                    in nested.namelist()
                    if not name.endswith("/")
                ]

                if not names:

                    raise DataInsufficientError(
                        "SPRE interno vazio."
                    )

                payload = nested.read(
                    names[0]
                )

        except zipfile.BadZipFile:
            pass

    text = _decode_text(
        payload
    )

    raw = _read_delimited_text(
        text
    )

    return normalize_spre_dataframe(
        raw,
        trade_date,
    )


# ============================================================
# SPRE — ANO CORRENTE
# ============================================================

def load_current_year_spre():

    if not CURRENT_YEAR_DIR.exists():

        raise DataInsufficientError(
            "Diretório B3 do ano corrente "
            "não encontrado: "
            f"{CURRENT_YEAR_DIR}"
        )

    files = sorted(
        list(
            CURRENT_YEAR_DIR.glob(
                "SPRE*.zip"
            )
        )
        +
        list(
            CURRENT_YEAR_DIR.glob(
                "SPRE*.ZIP"
            )
        )
    )

    # Evita duplicidade em sistemas
    # case-insensitive.
    unique_files = []

    seen = set()

    for path in files:

        resolved = str(
            path.resolve()
        )

        if resolved in seen:
            continue

        seen.add(
            resolved
        )

        unique_files.append(
            path
        )

    if not unique_files:

        raise DataInsufficientError(
            "Nenhum arquivo SPRE do "
            "ano corrente foi encontrado."
        )

    frames = []

    failures = []

    for path in unique_files:

        try:

            df = parse_spre_zip(
                path
            )

            if not df.empty:

                frames.append(
                    df
                )

        except Exception as exc:

            failures.append(
                {
                    "file":
                        path.name,

                    "error":
                        str(exc),
                }
            )

    if not frames:

        sample = (
            failures[:5]
        )

        raise DataInsufficientError(
            "Nenhum SPRE do ano corrente "
            "pôde ser normalizado. "
            f"Amostra de erros: {sample}"
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    return (
        result,
        failures,
    )


# ============================================================
# CONSOLIDAÇÃO
# ============================================================

def consolidate_market_history(
    historical: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:

    market = pd.concat(
        [
            historical,
            current,
        ],
        ignore_index=True,
    )

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

    market = market.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    market = market[
        market["VOLTOT"] >= 0
    ]

    # Se houver mais de um registro do
    # mesmo ticker no mesmo pregão,
    # consolidamos o volume financeiro.
    market = (
        market.groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
        )
        .agg(
            VOLTOT=(
                "VOLTOT",
                "sum",
            )
        )
    )

    market = (
        market
        .sort_values(
            [
                "DATA",
                "TICKER",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return market


# ============================================================
# AUDITORIA
# ============================================================

def audit_market_history(
    market: pd.DataFrame,
):

    if market.empty:

        raise DataInsufficientError(
            "Base B3 consolidada vazia."
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

        raise B3MarketHistoryError(
            "Base consolidada sem colunas: "
            + ", ".join(
                sorted(missing)
            )
        )

    if market.duplicated(
        subset=[
            "TICKER",
            "DATA",
        ]
    ).any():

        raise B3MarketHistoryError(
            "Duplicidade TICKER/DATA "
            "na base consolidada."
        )

    latest_date = (
        market["DATA"].max()
    )

    earliest_date = (
        market["DATA"].min()
    )

    if pd.isna(latest_date):

        raise DataInsufficientError(
            "Última data B3 inválida."
        )

    if latest_date.year != CURRENT_YEAR:

        raise DataInsufficientError(
            "Ano corrente B3 ainda não "
            "foi incorporado. "
            f"Última data: {latest_date.date()}"
        )

    return {
        "first_date":
            earliest_date.date().isoformat(),

        "latest_date":
            latest_date.date().isoformat(),

        "rows":
            int(len(market)),

        "tickers":
            int(
                market[
                    "TICKER"
                ].nunique()
            ),
    }


# ============================================================
# BUILD
# ============================================================

def build_b3_market_history():

    print(
        "=" * 72
    )

    print(
        "B3 INVESTMENT ENGINE — "
        "BUILD MARKET HISTORY V1"
    )

    print(
        "=" * 72
    )

    print(
        "\n[1/3] COTAHIST histórico..."
    )

    (
        historical,
        years_loaded,
    ) = load_historical_cotahist()

    print(
        "Anos históricos:",
        years_loaded,
    )

    print(
        "Registros históricos:",
        len(historical),
    )

    print(
        "\n[2/3] B3 ano corrente "
        "BVBG.186.01..."
    )

    (
        current,
        current_failures,
    ) = load_current_year_spre()

    print(
        "Registros ano corrente:",
        len(current),
    )

    print(
        "Arquivos SPRE ignorados:",
        len(current_failures),
    )

    print(
        "\n[3/3] Consolidação..."
    )

    market = (
        consolidate_market_history(
            historical,
            current,
        )
    )

    audit = audit_market_history(
        market
    )

    write_csv_atomic(
        market[
            [
                "TICKER",
                "DATA",
                "VOLTOT",
            ]
        ],
        OUTPUT_FILE,
    )

    manifest = {

        "engine":
            "B3_INVESTMENT_ENGINE",

        "module":
            "build_b3_market_history",

        "version":
            METHODOLOGY_VERSION,

        "generated_at_utc":
            utc_now_iso(),

        "status":
            "OK",

        "source_historical":
            "B3 COTAHIST",

        "source_current_year":
            "B3 BVBG.186.01",

        "historical_years":
            years_loaded,

        "current_year":
            CURRENT_YEAR,

        "first_market_date":
            audit[
                "first_date"
            ],

        "latest_market_date":
            audit[
                "latest_date"
            ],

        "rows":
            audit[
                "rows"
            ],

        "tickers":
            audit[
                "tickers"
            ],

        "current_year_parse_failures":
            current_failures,

        "methodology": {

            "quality_changed":
                False,

            "valuation_changed":
                False,

            "investability_changed":
                False,

            "technical_changed":
                False,

            "minimum_history_years":
                10,

            "minimum_daily_liquidity_brl":
                6_000_000,
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

    print(
        "\n"
        + "=" * 72
    )

    print(
        "B3 MARKET HISTORY — OK"
    )

    print(
        "Primeira data:",
        audit[
            "first_date"
        ],
    )

    print(
        "Última data:",
        audit[
            "latest_date"
        ],
    )

    print(
        "Registros:",
        audit[
            "rows"
        ],
    )

    print(
        "Tickers:",
        audit[
            "tickers"
        ],
    )

    print(
        "Saída:",
        OUTPUT_FILE,
    )

    print(
        "=" * 72
    )

    return market


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        build_b3_market_history()

        return 0

    except DataInsufficientError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            exc,
            file=sys.stderr,
        )

        return 3

    except Exception as exc:

        print(
            "\nERROR:",
            repr(exc),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
