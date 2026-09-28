"""
B3 INVESTMENT ENGINE
BUILD B3 MARKET HISTORY — V2

Objetivo
--------
Construir a base oficial normalizada de negociação utilizada pelo
B3 Investability Engine.

Fontes
------
1. COTAHIST anual oficial B3
   - histórico de negociação;
   - volume financeiro oficial (VOLTOT).

2. BVBG.186.01 / Simplified Price Report — Equities
   - ano corrente;
   - XML oficial B3;
   - utilizado para preços e confirmação da data/ticker;
   - NÃO utilizado para inventar volume financeiro.

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
- substitui o Investability Engine;
- converte quantidade de negócios em volume financeiro.

Metodologia congelada:
- histórico mínimo: 10 anos;
- liquidez média diária mínima: R$ 6 milhões.

O BVBG.186.01 real foi validado como:
ZIP externo
    -> ZIP interno
        -> XML BVBG.186.01

Campos observados no XML:
TradDt / Dt
TckrSymb
FrstPric
MinPric
MaxPric
TradAvrgPric
LastPric
RglrTxsQty

O arquivo NÃO contém VOLTOT.

Consequentemente:
- COTAHIST continua sendo a fonte oficial de VOLTOT;
- SPRE fornece preços do ano corrente;
- ausência de VOLTOT no SPRE nunca é mascarada.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

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

SPRE_PRICE_FILE = (
    B3_DIR / "spre_prices_live.csv"
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
    "B3_MARKET_HISTORY_V2_XML"
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


def local_name(
    tag: str,
) -> str:

    if "}" in tag:
        return tag.rsplit(
            "}",
            1,
        )[1]

    return tag


def safe_float(
    value,
):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# COTAHIST — FIXED WIDTH
# ============================================================

def parse_cotahist_line(
    line: str,
):

    """
    Layout oficial COTAHIST necessário ao projeto.

    Campos utilizados:

    TIPREG
        posições 1-2

    DATA
        posições 3-10

    CODNEG
        posições 13-24

    TPMERC
        posições 25-27

    VOLTOT
        posições 171-188
        valor com 2 casas decimais implícitas
    """

    if len(line) < 188:
        return None

    tipreg = (
        line[0:2]
        .strip()
    )

    if tipreg != "01":
        return None

    data_raw = (
        line[2:10]
        .strip()
    )

    ticker = (
        line[12:24]
        .strip()
        .upper()
    )

    tpmerc = (
        line[24:27]
        .strip()
    )

    if tpmerc != VALID_MARKET_TYPE:
        return None

    if not ticker:
        return None

    try:

        data = pd.to_datetime(
            data_raw,
            format="%Y%m%d",
            errors="raise",
        )

    except Exception:
        return None

    vol_raw = (
        line[170:188]
        .strip()
    )

    try:

        voltot = (
            int(vol_raw)
            / 100.0
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return {
        "TICKER":
            ticker,

        "DATA":
            data,

        "VOLTOT":
            float(voltot),

        "SOURCE":
            "B3_COTAHIST",
    }


def parse_cotahist_text(
    text: str,
) -> pd.DataFrame:

    records = []

    for line in text.splitlines():

        row = parse_cotahist_line(
            line
        )

        if row is not None:

            records.append(
                row
            )

    if not records:

        return pd.DataFrame(
            columns=[
                "TICKER",
                "DATA",
                "VOLTOT",
                "SOURCE",
            ]
        )

    return pd.DataFrame(
        records
    )


def parse_cotahist_zip(
    path: Path,
) -> pd.DataFrame:

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
                    "COTAHIST vazio: "
                    f"{path}"
                )

            candidates = [
                name
                for name
                in names
                if name.lower().endswith(
                    ".txt"
                )
            ]

            if candidates:

                name = candidates[0]

            else:

                name = names[0]

            payload = archive.read(
                name
            )

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            "COTAHIST ZIP inválido: "
            f"{path}"
        ) from exc

    text = None

    for encoding in (
        "latin-1",
        "utf-8",
        "utf-8-sig",
    ):

        try:

            text = payload.decode(
                encoding
            )

            break

        except UnicodeDecodeError:
            continue

    if text is None:

        raise DataInsufficientError(
            "Não foi possível decodificar "
            f"COTAHIST: {path}"
        )

    return parse_cotahist_text(
        text
    )


def load_historical_cotahist():

    if not HISTORICAL_DIR.exists():

        raise DataInsufficientError(
            "Diretório COTAHIST não "
            "encontrado: "
            f"{HISTORICAL_DIR}"
        )

    files = sorted(
        list(
            HISTORICAL_DIR.glob(
                "COTAHIST_A*.ZIP"
            )
        )
        +
        list(
            HISTORICAL_DIR.glob(
                "COTAHIST_A*.zip"
            )
        )
    )

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
            "Nenhum COTAHIST anual "
            "foi encontrado."
        )

    frames = []
    years_loaded = []

    for path in unique_files:

        match = re.search(
            r"COTAHIST_A(\d{4})",
            path.name.upper(),
        )

        if not match:
            continue

        year = int(
            match.group(1)
        )

        df = parse_cotahist_zip(
            path
        )

        if df.empty:
            continue

        frames.append(
            df
        )

        years_loaded.append(
            year
        )

    if not frames:

        raise DataInsufficientError(
            "Nenhum COTAHIST válido "
            "foi carregado."
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result["TICKER"] = (
        result["TICKER"]
        .map(normalize_ticker)
    )

    result["DATA"] = (
        pd.to_datetime(
            result["DATA"],
            errors="coerce",
        )
    )

    result["VOLTOT"] = (
        pd.to_numeric(
            result["VOLTOT"],
            errors="coerce",
        )
    )

    result = result.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    result = result[
        result["VOLTOT"] >= 0
    ].copy()

    result = (
        result
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

    years_loaded = sorted(
        set(
            years_loaded
        )
    )

    return (
        result,
        years_loaded,
    )


# ============================================================
# SPRE — ZIP / XML
# ============================================================

def _read_outer_zip(
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
                    "SPRE externo vazio: "
                    f"{path.name}"
                )

            preferred = [
                name
                for name
                in names
                if name.lower().endswith(
                    (
                        ".zip",
                        ".xml",
                    )
                )
            ]

            name = (
                preferred[0]
                if preferred
                else names[0]
            )

            return archive.read(
                name
            )

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            "SPRE externo inválido: "
            f"{path}"
        ) from exc


def _extract_spre_xml(
    path: Path,
) -> bytes:

    """
    Estrutura real validada:

    SPREYYMMDD.zip
        -> SPREYYMMDD.zip
            -> BVBG.186.01_....xml

    Também aceita XML diretamente dentro
    do ZIP externo caso a B3 altere apenas
    o empacotamento, sem alterar o conteúdo.
    """

    payload = _read_outer_zip(
        path
    )

    depth = 0

    while payload[:2] == b"PK":

        depth += 1

        if depth > 4:

            raise DataInsufficientError(
                "SPRE possui níveis ZIP "
                "excessivos."
            )

        try:

            with zipfile.ZipFile(
                io.BytesIO(
                    payload
                ),
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
                        "ZIP interno SPRE vazio."
                    )

                xml_candidates = [
                    name
                    for name
                    in names
                    if name.lower().endswith(
                        ".xml"
                    )
                ]

                zip_candidates = [
                    name
                    for name
                    in names
                    if name.lower().endswith(
                        ".zip"
                    )
                ]

                if xml_candidates:

                    payload = nested.read(
                        xml_candidates[0]
                    )

                    break

                if zip_candidates:

                    payload = nested.read(
                        zip_candidates[0]
                    )

                    continue

                payload = nested.read(
                    names[0]
                )

        except zipfile.BadZipFile as exc:

            raise DataInsufficientError(
                "ZIP interno SPRE inválido."
            ) from exc

    stripped = payload.lstrip()

    if not stripped.startswith(
        b"<?xml"
    ) and not stripped.startswith(
        b"<"
    ):

        raise DataInsufficientError(
            "Conteúdo SPRE não é XML."
        )

    return payload


# ============================================================
# SPRE — XML BVBG.186.01
# ============================================================

def _element_values(
    element,
) -> dict:

    values = {}

    for child in element.iter():

        if child is element:
            continue

        key = local_name(
            child.tag
        )

        text = (
            child.text or ""
        ).strip()

        if text:

            values[key] = text

    return values


def parse_spre_xml(
    payload: bytes,
    filename_trade_date: pd.Timestamp,
) -> pd.DataFrame:

    """
    Parser streaming.

    O XML real pode ter dezenas de MB.
    Portanto não carregamos a árvore inteira
    na memória.

    Unidade lógica observada:
        PricRpt

    Campos extraídos:
        TradDt/Dt
        TckrSymb
        FrstPric
        MinPric
        MaxPric
        TradAvrgPric
        LastPric
        RglrTxsQty
    """

    records = []

    stream = io.BytesIO(
        payload
    )

    try:

        context = ET.iterparse(
            stream,
            events=(
                "end",
            ),
        )

        for _, elem in context:

            if local_name(
                elem.tag
            ) != "PricRpt":

                continue

            values = _element_values(
                elem
            )

            ticker = normalize_ticker(
                values.get(
                    "TckrSymb"
                )
            )

            if not ticker:

                elem.clear()
                continue

            date_value = (
                values.get(
                    "Dt"
                )
                or
                values.get(
                    "TradDt"
                )
            )

            if date_value:

                trade_date = pd.to_datetime(
                    date_value,
                    errors="coerce",
                )

            else:

                trade_date = (
                    filename_trade_date
                )

            if pd.isna(
                trade_date
            ):

                elem.clear()
                continue

            records.append(
                {
                    "TICKER":
                        ticker,

                    "DATA":
                        trade_date,

                    "FIRST_PRICE":
                        safe_float(
                            values.get(
                                "FrstPric"
                            )
                        ),

                    "LOW_PRICE":
                        safe_float(
                            values.get(
                                "MinPric"
                            )
                        ),

                    "HIGH_PRICE":
                        safe_float(
                            values.get(
                                "MaxPric"
                            )
                        ),

                    "AVG_PRICE":
                        safe_float(
                            values.get(
                                "TradAvrgPric"
                            )
                        ),

                    "LAST_PRICE":
                        safe_float(
                            values.get(
                                "LastPric"
                            )
                        ),

                    "REGULAR_TRADES_QTY":
                        safe_float(
                            values.get(
                                "RglrTxsQty"
                            )
                        ),

                    "SOURCE":
                        "B3_BVBG_186_01",
                }
            )

            elem.clear()

    except ET.ParseError as exc:

        raise DataInsufficientError(
            "XML BVBG.186.01 inválido."
        ) from exc

    if not records:

        raise DataInsufficientError(
            "Nenhum PricRpt válido foi "
            "encontrado no BVBG.186.01."
        )

    df = pd.DataFrame(
        records
    )

    df["DATA"] = pd.to_datetime(
        df["DATA"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "TICKER",
            "DATA",
        ]
    )

    # Não convertemos RglrTxsQty em VOLTOT.
    # São grandezas diferentes.

    return (
        df
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

    filename_trade_date = (
        pd.to_datetime(
            date_code,
            format="%y%m%d",
            errors="raise",
        )
    )

    payload = _extract_spre_xml(
        path
    )

    df = parse_spre_xml(
        payload,
        filename_trade_date,
    )

    if df.empty:

        raise DataInsufficientError(
            "SPRE sem registros válidos: "
            f"{path.name}"
        )

    return df


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

        raise DataInsufficientError(
            "Nenhum SPRE do ano corrente "
            "pôde ser normalizado. "
            f"Erros: {failures[:5]}"
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result = (
        result
        .sort_values(
            [
                "DATA",
                "TICKER",
            ]
        )
        .drop_duplicates(
            subset=[
                "DATA",
                "TICKER",
            ],
            keep="last",
        )
        .reset_index(
            drop=True
        )
    )

    return (
        result,
        failures,
    )


# ============================================================
# CONSOLIDAÇÃO COTAHIST
# ============================================================

def consolidate_market_history(
    historical: pd.DataFrame,
) -> pd.DataFrame:

    """
    A base de liquidez é construída somente
    com observações que possuem VOLTOT oficial.

    O SPRE não entra nesta concatenação porque
    BVBG.186.01 não fornece VOLTOT.

    Isso evita adulteração da regra congelada
    de liquidez média diária.
    """

    required = {
        "TICKER",
        "DATA",
        "VOLTOT",
    }

    missing = (
        required
        -
        set(
            historical.columns
        )
    )

    if missing:

        raise DataInsufficientError(
            "COTAHIST sem colunas obrigatórias: "
            f"{sorted(missing)}"
        )

    market = historical[
        [
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    ].copy()

    market["TICKER"] = (
        market["TICKER"]
        .map(normalize_ticker)
    )

    market["DATA"] = (
        pd.to_datetime(
            market["DATA"],
            errors="coerce",
        )
    )

    market["VOLTOT"] = (
        pd.to_numeric(
            market["VOLTOT"],
            errors="coerce",
        )
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
    ].copy()

    # Caso existam registros duplicados,
    # soma-se o volume financeiro do mesmo
    # ticker na mesma sessão.

    market = (
        market
        .groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
        )["VOLTOT"]
        .sum()
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
    spre_prices: pd.DataFrame,
):

    if market.empty:

        raise DataInsufficientError(
            "Market history vazio."
        )

    if spre_prices.empty:

        raise DataInsufficientError(
            "SPRE de preços vazio."
        )

    historical_latest = (
        market["DATA"].max()
    )

    historical_first = (
        market["DATA"].min()
    )

    spre_latest = (
        spre_prices["DATA"].max()
    )

    spre_first = (
        spre_prices["DATA"].min()
    )

    if pd.isna(
        historical_latest
    ):

        raise DataInsufficientError(
            "Última data COTAHIST inválida."
        )

    if pd.isna(
        spre_latest
    ):

        raise DataInsufficientError(
            "Última data SPRE inválida."
        )

    if spre_latest.year != CURRENT_YEAR:

        raise DataInsufficientError(
            "Ano corrente B3 não confirmado "
            "pelo SPRE. "
            f"Última data: {spre_latest.date()}"
        )

    return {
        "historical_first_date":
            historical_first.date().isoformat(),

        "historical_latest_date":
            historical_latest.date().isoformat(),

        "spre_first_date":
            spre_first.date().isoformat(),

        "spre_latest_date":
            spre_latest.date().isoformat(),

        "liquidity_rows":
            int(
                len(
                    market
                )
            ),

        "liquidity_tickers":
            int(
                market[
                    "TICKER"
                ].nunique()
            ),

        "spre_rows":
            int(
                len(
                    spre_prices
                )
            ),

        "spre_tickers":
            int(
                spre_prices[
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
        "BUILD MARKET HISTORY V2 XML"
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
        "BVBG.186.01 XML..."
    )

    (
        spre_prices,
        current_failures,
    ) = load_current_year_spre()

    print(
        "Registros SPRE:",
        len(spre_prices),
    )

    print(
        "Tickers SPRE:",
        spre_prices[
            "TICKER"
        ].nunique(),
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
            historical
        )
    )

    audit = audit_market_history(
        market,
        spre_prices,
    )

    # --------------------------------------------------------
    # LIQUIDEZ
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # PREÇOS SPRE
    # --------------------------------------------------------

    write_csv_atomic(
        spre_prices[
            [
                "TICKER",
                "DATA",
                "FIRST_PRICE",
                "LOW_PRICE",
                "HIGH_PRICE",
                "AVG_PRICE",
                "LAST_PRICE",
                "REGULAR_TRADES_QTY",
                "SOURCE",
            ]
        ],
        SPRE_PRICE_FILE,
    )

    # --------------------------------------------------------
    # MANIFEST
    # --------------------------------------------------------

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
            "OK_WITH_SOURCE_LIMITATION",

        "source_historical":
            "B3 COTAHIST",

        "source_current_year":
            "B3 BVBG.186.01",

        "historical_years":
            years_loaded,

        "current_year":
            CURRENT_YEAR,

        "historical_first_date":
            audit[
                "historical_first_date"
            ],

        "historical_latest_date":
            audit[
                "historical_latest_date"
            ],

        "spre_first_date":
            audit[
                "spre_first_date"
            ],

        "spre_latest_date":
            audit[
                "spre_latest_date"
            ],

        "liquidity_rows":
            audit[
                "liquidity_rows"
            ],

        "liquidity_tickers":
            audit[
                "liquidity_tickers"
            ],

        "spre_rows":
            audit[
                "spre_rows"
            ],

        "spre_tickers":
            audit[
                "spre_tickers"
            ],

        "current_year_parse_failures":
            current_failures,

        "source_limitation": {
            "bvbg_186_01_contains_voltot":
                False,

            "regular_transactions_used_as_voltot":
                False,

            "liquidity_source":
                "B3_COTAHIST_ONLY",

            "current_year_price_source":
                "B3_BVBG_186_01",
        },

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

        "output_liquidity_file":
            str(
                OUTPUT_FILE
            ),

        "output_spre_price_file":
            str(
                SPRE_PRICE_FILE
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
        "COTAHIST primeira data:",
        audit[
            "historical_first_date"
        ],
    )

    print(
        "COTAHIST última data:",
        audit[
            "historical_latest_date"
        ],
    )

    print(
        "SPRE última data:",
        audit[
            "spre_latest_date"
        ],
    )

    print(
        "Registros liquidez:",
        audit[
            "liquidity_rows"
        ],
    )

    print(
        "Tickers liquidez:",
        audit[
            "liquidity_tickers"
        ],
    )

    print(
        "Registros SPRE:",
        audit[
            "spre_rows"
        ],
    )

    print(
        "Tickers SPRE:",
        audit[
            "spre_tickers"
        ],
    )

    print(
        "\nATENÇÃO:"
    )

    print(
        "BVBG.186.01 não fornece VOLTOT."
    )

    print(
        "RglrTxsQty NÃO foi convertido "
        "em volume financeiro."
    )

    print(
        "Metodologia de liquidez preservada."
    )

    print(
        "\nSaída liquidez:",
        OUTPUT_FILE,
    )

    print(
        "Saída preços SPRE:",
        SPRE_PRICE_FILE,
    )

    print(
        "=" * 72
    )

    return {
        "market_history":
            market,

        "spre_prices":
            spre_prices,

        "audit":
            audit,
    }


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
