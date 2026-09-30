# ============================================================
# B3 INVESTMENT ENGINE
# BUILD B3 MARKET HISTORY — V6 BATCHED PERSISTENT CACHE
# ============================================================
#
# OBJETIVO
# ------------------------------------------------------------
# Construir e manter:
#
# 1. data/live/b3/market_history_live.csv
#    - histórico oficial de preços OHLC e liquidez;
#    - fonte: B3 COTAHIST;
#    - OPEN/HIGH/LOW/CLOSE oficiais;
#    - VOLTOT oficial.
#
# 2. data/live/b3/spre_prices_live.csv
#    - preços oficiais do ano corrente;
#    - fonte: B3 BVBG.186.01;
#    - NÃO transforma RglrTxsQty em VOLTOT.
#
# ARQUITETURA V6
# ------------------------------------------------------------
# - cache particionado por arquivo-fonte;
# - cada COTAHIST anual gera sua própria partição;
# - cada SPRE gera sua própria partição;
# - fonte já processada e inalterada não é reprocessada;
# - identidade da fonte usa SHA-256 e não mtime;
# - SPRE é processado em LOTES recuperáveis;
# - cada execução processa quantidade limitada de SPRE;
# - estado é salvo após CADA partição;
# - execução encerra normalmente quando ainda existem
#   partições SPRE pendentes;
# - consolidação global ocorre somente quando todas as
#   partições necessárias estão prontas;
# - arquivos novos entram normalmente;
# - metodologia financeira permanece congelada.
#
# IMPORTANTE
# ------------------------------------------------------------
# Este módulo NÃO altera:
# - Sector Engine;
# - Quality Engine;
# - Investability Engine;
# - Valuation Engine;
# - Technical Engine.
#
# Regras congeladas:
# - histórico mínimo: 10 anos;
# - liquidez média diária: R$ 6 milhões;
# - SPRE NÃO fornece VOLTOT;
# - RglrTxsQty NÃO é volume financeiro.
#
# CONTROLE DE LOTE
# ------------------------------------------------------------
# Variável opcional:
#
# B3_MARKET_HISTORY_SPRE_BATCH_SIZE
#
# Default: 25 arquivos SPRE por execução.
#
# O workflow deve persistir:
#
# data/live/b3/cache/market_history_v6
#
# após cada execução.
# ============================================================

from __future__ import annotations

import hashlib
import io
import json
import os
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

HISTORICAL_DIR = B3_DIR / "cotahist"
CURRENT_YEAR_DIR = B3_DIR / "current_year"

OUTPUT_FILE = B3_DIR / "market_history_live.csv"
SPRE_PRICE_FILE = B3_DIR / "spre_prices_live.csv"
MANIFEST_FILE = B3_DIR / "market_history_manifest.json"

CACHE_ROOT = B3_DIR / "cache" / "market_history_v6"

COTAHIST_CACHE_DIR = CACHE_ROOT / "cotahist_parts"
SPRE_CACHE_DIR = CACHE_ROOT / "spre_parts"

STATE_FILE = CACHE_ROOT / "state.json"
BUILD_STATUS_FILE = CACHE_ROOT / "build_status.json"


# ============================================================
# CONSTANTS
# ============================================================

CURRENT_YEAR = datetime.now(timezone.utc).year

VALID_MARKET_TYPE = "010"

METHODOLOGY_VERSION = (
    "B3_MARKET_HISTORY_V6_BATCHED_PERSISTENT_CACHE"
)

STATE_VERSION = 3

MINIMUM_HISTORY_YEARS = 10
MINIMUM_DAILY_LIQUIDITY_BRL = 6_000_000

DEFAULT_SPRE_BATCH_SIZE = 25

SPRE_COLUMNS = [
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


# ============================================================
# DIRECTORIES
# ============================================================

for directory in [
    B3_DIR,
    CACHE_ROOT,
    COTAHIST_CACHE_DIR,
    SPRE_CACHE_DIR,
]:
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# EXCEPTIONS
# ============================================================

class B3MarketHistoryError(RuntimeError):
    pass


class DataInsufficientError(B3MarketHistoryError):
    pass


# ============================================================
# UTILITIES
# ============================================================

def utc_now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def log(*args) -> None:

    print(
        *args,
        flush=True,
    )


def write_json_atomic(
    data: dict,
    path: Path,
) -> None:

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


def write_csv_atomic(
    df: pd.DataFrame,
    path: Path,
) -> None:

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


def normalize_ticker(value):

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


def local_name(tag: str) -> str:

    if "}" in tag:
        return tag.rsplit(
            "}",
            1,
        )[1]

    return tag


def safe_float(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def get_spre_batch_size() -> int:

    raw = os.getenv(
        "B3_MARKET_HISTORY_SPRE_BATCH_SIZE",
        str(DEFAULT_SPRE_BATCH_SIZE),
    )

    try:
        value = int(raw)

    except (
        TypeError,
        ValueError,
    ):
        value = DEFAULT_SPRE_BATCH_SIZE

    if value < 1:
        value = DEFAULT_SPRE_BATCH_SIZE

    return value


# ============================================================
# SOURCE IDENTITY
# ============================================================
#
# mtime NÃO é utilizado.
#
# GitHub runners podem recriar arquivos com timestamps
# diferentes mesmo quando o conteúdo oficial é idêntico.
# ============================================================

def sha256_file(
    path: Path,
) -> str:

    h = hashlib.sha256()

    with path.open("rb") as stream:

        for chunk in iter(
            lambda: stream.read(
                1024 * 1024
            ),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def source_identity(
    path: Path,
) -> dict:

    return {
        "filename": path.name,
        "size_bytes": int(
            path.stat().st_size
        ),
        "sha256": sha256_file(path),
    }


def same_identity(
    old: dict | None,
    new: dict,
) -> bool:

    if not old:
        return False

    return (
        old.get("filename")
        == new.get("filename")
        and
        int(
            old.get(
                "size_bytes",
                -1,
            )
        )
        ==
        int(
            new.get(
                "size_bytes",
                -2,
            )
        )
        and
        old.get("sha256")
        == new.get("sha256")
    )


# ============================================================
# STATE
# ============================================================

def empty_state() -> dict:

    return {
        "state_version": STATE_VERSION,
        "generated_at_utc": utc_now_iso(),
        "cotahist": {},
        "spre": {},
    }


def load_state() -> dict:

    if not STATE_FILE.exists():
        return empty_state()

    try:

        state = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return empty_state()

    if not isinstance(
        state,
        dict,
    ):
        return empty_state()

    #
    # Migração segura V5 -> V6.
    #
    # As identidades das fontes permanecem válidas.
    #

    if not isinstance(
        state.get("cotahist"),
        dict,
    ):
        state["cotahist"] = {}

    if not isinstance(
        state.get("spre"),
        dict,
    ):
        state["spre"] = {}

    state["state_version"] = STATE_VERSION

    return state


def save_state(
    state: dict,
) -> None:

    state["state_version"] = STATE_VERSION
    state["generated_at_utc"] = utc_now_iso()

    write_json_atomic(
        state,
        STATE_FILE,
    )


# ============================================================
# BUILD STATUS
# ============================================================

def write_build_status(
    *,
    complete: bool,
    phase: str,
    total_spre: int = 0,
    ready_spre: int = 0,
    pending_spre: int = 0,
    processed_now: int = 0,
    message: str = "",
) -> None:

    payload = {
        "engine": "B3_INVESTMENT_ENGINE",
        "module": "build_b3_market_history",
        "version": METHODOLOGY_VERSION,
        "generated_at_utc": utc_now_iso(),
        "complete": bool(complete),
        "phase": phase,
        "current_year": CURRENT_YEAR,
        "spre_total": int(total_spre),
        "spre_ready": int(ready_spre),
        "spre_pending": int(pending_spre),
        "spre_processed_now": int(processed_now),
        "message": message,
    }

    write_json_atomic(
        payload,
        BUILD_STATUS_FILE,
    )


# ============================================================
# CACHE PATHS
# ============================================================

def safe_cache_name(
    filename: str,
) -> str:

    return re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        filename,
    )


def cotahist_cache_path(
    source: Path,
) -> Path:

    return (
        COTAHIST_CACHE_DIR
        /
        f"{safe_cache_name(source.name)}.csv"
    )


def spre_cache_path(
    source: Path,
) -> Path:

    return (
        SPRE_CACHE_DIR
        /
        f"{safe_cache_name(source.name)}.csv"
    )


# ============================================================
# EMPTY DATAFRAMES
# ============================================================

def empty_market() -> pd.DataFrame:

    return pd.DataFrame(
        columns=[
            "TICKER",
            "DATA",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
            "VOLTOT",
        ]
    )


def empty_spre() -> pd.DataFrame:

    return pd.DataFrame(
        columns=SPRE_COLUMNS
    )


# ============================================================
# COTAHIST PARSER
# ============================================================

def parse_cotahist_line(
    line: str,
):

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

    # COTAHIST fixed-width official price fields (BRL, 2 decimals)
    open_raw = line[56:69].strip()
    high_raw = line[69:82].strip()
    low_raw = line[82:95].strip()
    close_raw = line[108:121].strip()
    vol_raw = line[170:188].strip()

    try:

        open_price = int(open_raw) / 100.0
        high_price = int(high_raw) / 100.0
        low_price = int(low_raw) / 100.0
        close_price = int(close_raw) / 100.0
        voltot = int(vol_raw) / 100.0

    except (
        TypeError,
        ValueError,
    ):
        return None

    if (
        open_price <= 0
        or high_price <= 0
        or low_price <= 0
        or close_price <= 0
        or voltot < 0
    ):
        return None

    return {
        "TICKER": ticker,
        "DATA": data,
        "OPEN": float(open_price),
        "HIGH": float(high_price),
        "LOW": float(low_price),
        "CLOSE": float(close_price),
        "VOLTOT": float(voltot),
    }


def parse_cotahist_zip(
    path: Path,
) -> pd.DataFrame:

    records = []

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

            txt_candidates = [
                name
                for name
                in names
                if name.lower().endswith(
                    ".txt"
                )
            ]

            member = (
                txt_candidates[0]
                if txt_candidates
                else names[0]
            )

            with archive.open(
                member,
                "r",
            ) as stream:

                for raw_line in stream:

                    try:

                        line = raw_line.decode(
                            "latin-1"
                        )

                    except UnicodeDecodeError:

                        try:

                            line = raw_line.decode(
                                "utf-8"
                            )

                        except UnicodeDecodeError:
                            continue

                    row = parse_cotahist_line(
                        line
                    )

                    if row is not None:
                        records.append(row)

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            "COTAHIST ZIP inválido: "
            f"{path}"
        ) from exc

    if not records:
        return empty_market()

    df = pd.DataFrame(records)

    df["TICKER"] = (
        df["TICKER"]
        .map(normalize_ticker)
    )

    df["DATA"] = pd.to_datetime(
        df["DATA"],
        errors="coerce",
    )

    numeric_columns = [
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        "VOLTOT",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "TICKER",
            "DATA",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
            "VOLTOT",
        ]
    )

    df = df[
        (df["OPEN"] > 0)
        & (df["HIGH"] > 0)
        & (df["LOW"] > 0)
        & (df["CLOSE"] > 0)
        & (df["VOLTOT"] >= 0)
    ].copy()

    df = (
        df
        .groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
            sort=False,
        )
        .agg(
            OPEN=("OPEN", "first"),
            HIGH=("HIGH", "max"),
            LOW=("LOW", "min"),
            CLOSE=("CLOSE", "last"),
            VOLTOT=("VOLTOT", "sum"),
        )
    )

    return df


# ============================================================
# SPRE ZIP / XML
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

            return archive.read(name)

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            "SPRE externo inválido: "
            f"{path}"
        ) from exc


def _extract_spre_xml(
    path: Path,
) -> bytes:

    payload = _read_outer_zip(path)

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

    if (
        not stripped.startswith(
            b"<?xml"
        )
        and
        not stripped.startswith(
            b"<"
        )
    ):

        raise DataInsufficientError(
            "Conteúdo SPRE não é XML."
        )

    return payload


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

    records = []

    stream = io.BytesIO(payload)

    try:

        context = ET.iterparse(
            stream,
            events=("end",),
        )

        for _, elem in context:

            if local_name(
                elem.tag
            ) != "PricRpt":
                continue

            values = _element_values(elem)

            ticker = normalize_ticker(
                values.get("TckrSymb")
            )

            if not ticker:

                elem.clear()
                continue

            date_value = (
                values.get("Dt")
                or
                values.get("TradDt")
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

            if pd.isna(trade_date):

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

    df = pd.DataFrame(records)

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

    return (
        df
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
        .reset_index(drop=True)
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

    filename_trade_date = pd.to_datetime(
        date_code,
        format="%y%m%d",
        errors="raise",
    )

    payload = _extract_spre_xml(path)

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
# SOURCE LISTING
# ============================================================

def unique_paths(
    paths: list[Path],
) -> list[Path]:

    output = []
    seen = set()

    for path in sorted(paths):

        key = str(path.resolve())

        if key in seen:
            continue

        seen.add(key)
        output.append(path)

    return output


def list_cotahist_files() -> list[Path]:

    if not HISTORICAL_DIR.exists():

        raise DataInsufficientError(
            "Diretório COTAHIST não encontrado: "
            f"{HISTORICAL_DIR}"
        )

    files = unique_paths(
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

    if not files:

        raise DataInsufficientError(
            "Nenhum COTAHIST anual "
            "foi encontrado."
        )

    return files


def list_spre_files() -> list[Path]:

    if not CURRENT_YEAR_DIR.exists():

        raise DataInsufficientError(
            "Diretório B3 do ano corrente "
            "não encontrado: "
            f"{CURRENT_YEAR_DIR}"
        )

    files = unique_paths(
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

    if not files:

        raise DataInsufficientError(
            "Nenhum arquivo SPRE do "
            "ano corrente foi encontrado."
        )

    return files


# ============================================================
# PARTITION VALIDATION
# ============================================================

def valid_cotahist_partition(
    path: Path,
) -> bool:

    if not path.exists():
        return False

    try:

        header = pd.read_csv(
            path,
            nrows=2,
        )

    except Exception:
        return False

    required = {
        "TICKER",
        "DATA",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        "VOLTOT",
    }

    return required.issubset(
        set(header.columns)
    )


def valid_spre_partition(
    path: Path,
) -> bool:

    if not path.exists():
        return False

    try:

        header = pd.read_csv(
            path,
            nrows=2,
        )

    except Exception:
        return False

    return {
        "TICKER",
        "DATA",
    }.issubset(
        set(header.columns)
    )


# ============================================================
# COTAHIST PARTITION UPDATE
# ============================================================

def update_cotahist_partitions(
    state: dict,
):

    files = list_cotahist_files()

    processed = 0
    unchanged = 0
    years = []

    for index, path in enumerate(
        files,
        start=1,
    ):

        match = re.search(
            r"COTAHIST_A(\d{4})",
            path.name.upper(),
        )

        if not match:
            continue

        year = int(
            match.group(1)
        )

        years.append(year)

        log(
            f"  COTAHIST "
            f"{index}/{len(files)} "
            f"- {path.name}"
        )

        identity = source_identity(path)

        partition = cotahist_cache_path(
            path
        )

        old_identity = (
            state["cotahist"]
            .get(path.name)
        )

        if (
            same_identity(
                old_identity,
                identity,
            )
            and
            valid_cotahist_partition(
                partition
            )
        ):

            log(
                "    ✓ CACHE VÁLIDO"
            )

            unchanged += 1
            continue

        log(
            "    PROCESSANDO..."
        )

        year_df = parse_cotahist_zip(
            path
        )

        if year_df.empty:

            raise DataInsufficientError(
                "COTAHIST sem registros válidos: "
                f"{path.name}"
            )

        year_df["DATA"] = (
            pd.to_datetime(
                year_df["DATA"],
                errors="coerce",
            )
            .dt.strftime(
                "%Y-%m-%d"
            )
        )

        write_csv_atomic(
            year_df,
            partition,
        )

        state["cotahist"][
            path.name
        ] = identity

        save_state(state)

        processed += 1

        log(
            "    ✓ PARTIÇÃO SALVA — "
            f"{len(year_df)} registros"
        )

    return (
        sorted(set(years)),
        {
            "files": len(files),
            "unchanged": unchanged,
            "processed": processed,
        },
    )


# ============================================================
# SPRE STATUS
# ============================================================

def inspect_spre_partitions(
    state: dict,
):

    files = list_spre_files()

    ready = []
    pending = []

    for path in files:

        identity = source_identity(
            path
        )

        partition = spre_cache_path(
            path
        )

        old_identity = (
            state["spre"]
            .get(path.name)
        )

        if (
            same_identity(
                old_identity,
                identity,
            )
            and
            valid_spre_partition(
                partition
            )
        ):

            ready.append(
                (
                    path,
                    identity,
                )
            )

        else:

            pending.append(
                (
                    path,
                    identity,
                )
            )

    return files, ready, pending


# ============================================================
# SPRE PARTITION UPDATE — V6 BATCHED
# ============================================================

def update_spre_partitions(
    state: dict,
    batch_size: int,
):

    (
        files,
        ready_before,
        pending_before,
    ) = inspect_spre_partitions(
        state
    )

    total_files = len(files)
    ready_count_before = len(
        ready_before
    )
    pending_count_before = len(
        pending_before
    )

    log(
        "SPRE total:",
        total_files,
    )

    log(
        "SPRE já prontos:",
        ready_count_before,
    )

    log(
        "SPRE pendentes:",
        pending_count_before,
    )

    log(
        "Limite desta execução:",
        batch_size,
    )

    if not pending_before:

        return (
            [],
            {
                "files": total_files,
                "unchanged": ready_count_before,
                "processed": 0,
                "ready": total_files,
                "pending": 0,
                "complete": True,
            },
        )

    selected = pending_before[
        :batch_size
    ]

    failures = []
    processed = 0

    for index, (
        path,
        identity,
    ) in enumerate(
        selected,
        start=1,
    ):

        log(
            f"  SPRE LOTE "
            f"{index}/{len(selected)} "
            f"- {path.name}"
        )

        partition = spre_cache_path(
            path
        )

        try:

            log(
                "    PROCESSANDO..."
            )

            day_df = parse_spre_zip(
                path
            )

            if day_df.empty:

                raise DataInsufficientError(
                    "SPRE vazio."
                )

            for column in SPRE_COLUMNS:

                if column not in day_df.columns:
                    day_df[column] = pd.NA

            day_df = day_df[
                SPRE_COLUMNS
            ].copy()

            day_df["DATA"] = (
                pd.to_datetime(
                    day_df["DATA"],
                    errors="coerce",
                )
                .dt.strftime(
                    "%Y-%m-%d"
                )
            )

            write_csv_atomic(
                day_df,
                partition,
            )

            #
            # CRÍTICO V6:
            # estado salvo imediatamente após a partição.
            #

            state["spre"][
                path.name
            ] = identity

            save_state(state)

            processed += 1

            log(
                "    ✓ PARTIÇÃO SALVA — "
                f"{len(day_df)} registros"
            )

        except Exception as exc:

            failures.append(
                {
                    "file": path.name,
                    "error": str(exc),
                }
            )

            log(
                "    ! FALHA:",
                str(exc),
            )

    (
        _,
        ready_after,
        pending_after,
    ) = inspect_spre_partitions(
        state
    )

    ready_count_after = len(
        ready_after
    )

    pending_count_after = len(
        pending_after
    )

    complete = (
        pending_count_after == 0
    )

    return (
        failures,
        {
            "files": total_files,
            "unchanged": ready_count_before,
            "processed": processed,
            "ready": ready_count_after,
            "pending": pending_count_after,
            "complete": complete,
        },
    )


# ============================================================
# REMOVE STALE CACHE
# ============================================================

def remove_stale_partitions(
    state: dict,
) -> None:

    current_cotahist = {
        path.name
        for path in list_cotahist_files()
    }

    current_spre = {
        path.name
        for path in list_spre_files()
    }

    stale_cotahist = [
        filename
        for filename
        in list(
            state["cotahist"].keys()
        )
        if filename not in current_cotahist
    ]

    stale_spre = [
        filename
        for filename
        in list(
            state["spre"].keys()
        )
        if filename not in current_spre
    ]

    for filename in stale_cotahist:

        partition = cotahist_cache_path(
            HISTORICAL_DIR / filename
        )

        if partition.exists():
            partition.unlink()

        state["cotahist"].pop(
            filename,
            None,
        )

    for filename in stale_spre:

        partition = spre_cache_path(
            CURRENT_YEAR_DIR / filename
        )

        if partition.exists():
            partition.unlink()

        state["spre"].pop(
            filename,
            None,
        )

    if stale_cotahist or stale_spre:
        save_state(state)


# ============================================================
# CONSOLIDATE COTAHIST ONCE
# ============================================================

def consolidate_cotahist(
    state: dict,
) -> pd.DataFrame:

    frames = []

    entries = sorted(
        state["cotahist"].keys()
    )

    if not entries:

        raise DataInsufficientError(
            "Nenhuma partição COTAHIST "
            "disponível."
        )

    log(
        "  Partições COTAHIST:",
        len(entries),
    )

    for index, filename in enumerate(
        entries,
        start=1,
    ):

        source = (
            HISTORICAL_DIR
            /
            filename
        )

        partition = cotahist_cache_path(
            source
        )

        if not valid_cotahist_partition(
            partition
        ):

            raise DataInsufficientError(
                "Partição COTAHIST ausente "
                "ou inválida: "
                f"{partition}"
            )

        log(
            f"    Lendo {index}/{len(entries)} "
            f"- {partition.name}"
        )

        df = pd.read_csv(
            partition,
            usecols=[
                "TICKER",
                "DATA",
                "OPEN",
                "HIGH",
                "LOW",
                "CLOSE",
                "VOLTOT",
            ],
            low_memory=False,
        )

        frames.append(df)

    market = pd.concat(
        frames,
        ignore_index=True,
    )

    del frames

    market["TICKER"] = (
        market["TICKER"]
        .map(normalize_ticker)
    )

    market["DATA"] = pd.to_datetime(
        market["DATA"],
        errors="coerce",
    )

    numeric_columns = [
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        "VOLTOT",
    ]

    for column in numeric_columns:

        market[column] = pd.to_numeric(
            market[column],
            errors="coerce",
        )

    market = market.dropna(
        subset=[
            "TICKER",
            "DATA",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
            "VOLTOT",
        ]
    )

    market = market[
        (market["OPEN"] > 0)
        & (market["HIGH"] > 0)
        & (market["LOW"] > 0)
        & (market["CLOSE"] > 0)
        & (market["VOLTOT"] >= 0)
    ].copy()

    market = (
        market
        .groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
            sort=False,
        )
        .agg(
            OPEN=("OPEN", "first"),
            HIGH=("HIGH", "max"),
            LOW=("LOW", "min"),
            CLOSE=("CLOSE", "last"),
            VOLTOT=("VOLTOT", "sum"),
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
        .reset_index(drop=True)
    )

    return market


# ============================================================
# CONSOLIDATE SPRE ONCE
# ============================================================

def consolidate_spre(
    state: dict,
) -> pd.DataFrame:

    frames = []

    entries = sorted(
        state["spre"].keys()
    )

    if not entries:

        raise DataInsufficientError(
            "Nenhuma partição SPRE disponível."
        )

    log(
        "  Partições SPRE:",
        len(entries),
    )

    for index, filename in enumerate(
        entries,
        start=1,
    ):

        source = (
            CURRENT_YEAR_DIR
            /
            filename
        )

        partition = spre_cache_path(
            source
        )

        if not valid_spre_partition(
            partition
        ):

            raise DataInsufficientError(
                "Partição SPRE ausente "
                "ou inválida: "
                f"{partition}"
            )

        if (
            index == 1
            or
            index % 25 == 0
            or
            index == len(entries)
        ):

            log(
                f"    Lendo SPRE "
                f"{index}/{len(entries)}"
            )

        df = pd.read_csv(
            partition,
            low_memory=False,
        )

        for column in SPRE_COLUMNS:

            if column not in df.columns:
                df[column] = pd.NA

        frames.append(
            df[SPRE_COLUMNS].copy()
        )

    if not frames:

        raise DataInsufficientError(
            "Nenhuma partição SPRE válida "
            "para consolidação."
        )

    spre = pd.concat(
        frames,
        ignore_index=True,
    )

    del frames

    spre["TICKER"] = (
        spre["TICKER"]
        .map(normalize_ticker)
    )

    spre["DATA"] = pd.to_datetime(
        spre["DATA"],
        errors="coerce",
    )

    numeric_columns = [
        "FIRST_PRICE",
        "LOW_PRICE",
        "HIGH_PRICE",
        "AVG_PRICE",
        "LAST_PRICE",
        "REGULAR_TRADES_QTY",
    ]

    for column in numeric_columns:

        spre[column] = pd.to_numeric(
            spre[column],
            errors="coerce",
        )

    spre = spre.dropna(
        subset=[
            "TICKER",
            "DATA",
        ]
    )

    spre = (
        spre
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
        .reset_index(drop=True)
    )

    return spre


# ============================================================
# AUDIT
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

    if pd.isna(historical_latest):

        raise DataInsufficientError(
            "Última data COTAHIST inválida."
        )

    if pd.isna(spre_latest):

        raise DataInsufficientError(
            "Última data SPRE inválida."
        )

    if spre_latest.year != CURRENT_YEAR:

        raise DataInsufficientError(
            "Ano corrente B3 não confirmado "
            "pelo SPRE. "
            f"Última data: "
            f"{spre_latest.date()}"
        )

    historical_years = sorted(
        market["DATA"]
        .dropna()
        .dt.year
        .unique()
        .tolist()
    )

    return {
        "historical_first_date":
            historical_first
            .date()
            .isoformat(),

        "historical_latest_date":
            historical_latest
            .date()
            .isoformat(),

        "historical_years":
            historical_years,

        "spre_first_date":
            spre_first
            .date()
            .isoformat(),

        "spre_latest_date":
            spre_latest
            .date()
            .isoformat(),

        "liquidity_rows":
            int(len(market)),

        "liquidity_tickers":
            int(
                market[
                    "TICKER"
                ].nunique()
            ),

        "spre_rows":
            int(len(spre_prices)),

        "spre_tickers":
            int(
                spre_prices[
                    "TICKER"
                ].nunique()
            ),
    }


# ============================================================
# PUBLICATION
# ============================================================

def publish_outputs(
    market: pd.DataFrame,
    spre: pd.DataFrame,
) -> None:

    log(
        "  Gravando market_history_live.csv "
        "UMA VEZ..."
    )

    market_out = market[
        [
            "TICKER",
            "DATA",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
            "VOLTOT",
        ]
    ].copy()

    market_out["DATA"] = (
        pd.to_datetime(
            market_out["DATA"],
            errors="coerce",
        )
        .dt.strftime(
            "%Y-%m-%d"
        )
    )

    write_csv_atomic(
        market_out,
        OUTPUT_FILE,
    )

    log(
        "    ✓ market_history_live.csv"
    )

    log(
        "  Gravando spre_prices_live.csv "
        "UMA VEZ..."
    )

    spre_out = spre[
        SPRE_COLUMNS
    ].copy()

    spre_out["DATA"] = (
        pd.to_datetime(
            spre_out["DATA"],
            errors="coerce",
        )
        .dt.strftime(
            "%Y-%m-%d"
        )
    )

    write_csv_atomic(
        spre_out,
        SPRE_PRICE_FILE,
    )

    log(
        "    ✓ spre_prices_live.csv"
    )


# ============================================================
# MANIFEST
# ============================================================

def build_manifest(
    *,
    audit: dict,
    cotahist_stats: dict,
    spre_stats: dict,
    failures: list,
) -> dict:

    return {
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

        "architecture":
            "BATCHED_PERSISTENT_CACHE",

        "source_historical":
            "B3 COTAHIST",

        "source_current_year":
            "B3 BVBG.186.01",

        "historical_years":
            audit[
                "historical_years"
            ],

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

        "incremental": {
            "cotahist_files":
                cotahist_stats[
                    "files"
                ],

            "cotahist_unchanged":
                cotahist_stats[
                    "unchanged"
                ],

            "cotahist_processed_now":
                cotahist_stats[
                    "processed"
                ],

            "spre_files":
                spre_stats[
                    "files"
                ],

            "spre_unchanged":
                spre_stats[
                    "unchanged"
                ],

            "spre_processed_now":
                spre_stats[
                    "processed"
                ],

            "spre_ready":
                spre_stats[
                    "ready"
                ],

            "spre_pending":
                spre_stats[
                    "pending"
                ],

            "spre_complete":
                spre_stats[
                    "complete"
                ],

            "spre_failures":
                failures,
        },

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
                MINIMUM_HISTORY_YEARS,

            "minimum_daily_liquidity_brl":
                MINIMUM_DAILY_LIQUIDITY_BRL,
        },

        "cache": {
            "root":
                str(CACHE_ROOT),

            "cotahist_parts":
                str(COTAHIST_CACHE_DIR),

            "spre_parts":
                str(SPRE_CACHE_DIR),

            "state_file":
                str(STATE_FILE),

            "build_status_file":
                str(BUILD_STATUS_FILE),
        },

        "output_liquidity_file":
            str(OUTPUT_FILE),

        "output_spre_price_file":
            str(SPRE_PRICE_FILE),
    }


# ============================================================
# BUILD
# ============================================================

def build_b3_market_history():

    log(
        "=" * 72
    )

    log(
        "B3 INVESTMENT ENGINE — "
        "BUILD MARKET HISTORY V6"
    )

    log(
        "BATCHED PERSISTENT CACHE"
    )

    log(
        "=" * 72
    )

    batch_size = get_spre_batch_size()

    log(
        "SPRE batch size:",
        batch_size,
    )

    # ========================================================
    # 1. STATE
    # ========================================================

    log(
        "\n[1/5] Carregando estado..."
    )

    state = load_state()

    log(
        "COTAHIST registrados:",
        len(state["cotahist"]),
    )

    log(
        "SPRE registrados:",
        len(state["spre"]),
    )

    # ========================================================
    # 2. COTAHIST PARTITIONS
    # ========================================================

    log(
        "\n[2/5] Atualizando partições COTAHIST..."
    )

    (
        years_loaded,
        cotahist_stats,
    ) = update_cotahist_partitions(
        state
    )

    log(
        "Anos disponíveis:",
        years_loaded,
    )

    log(
        "COTAHIST reaproveitados:",
        cotahist_stats["unchanged"],
    )

    log(
        "COTAHIST processados agora:",
        cotahist_stats["processed"],
    )

    # ========================================================
    # 3. SPRE PARTITIONS — BATCH
    # ========================================================

    log(
        "\n[3/5] Atualizando partições SPRE..."
    )

    (
        failures,
        spre_stats,
    ) = update_spre_partitions(
        state,
        batch_size,
    )

    log(
        "SPRE existentes no início:",
        spre_stats["unchanged"],
    )

    log(
        "SPRE processados agora:",
        spre_stats["processed"],
    )

    log(
        "SPRE prontos:",
        spre_stats["ready"],
    )

    log(
        "SPRE pendentes:",
        spre_stats["pending"],
    )

    log(
        "Falhas SPRE:",
        len(failures),
    )

    remove_stale_partitions(
        state
    )

    save_state(state)

    # ========================================================
    # V6 — CHECKPOINT DE SAÍDA
    # ========================================================

    if not spre_stats["complete"]:

        write_build_status(
            complete=False,
            phase="SPRE_PARTITIONS",
            total_spre=spre_stats["files"],
            ready_spre=spre_stats["ready"],
            pending_spre=spre_stats["pending"],
            processed_now=spre_stats["processed"],
            message=(
                "Lote SPRE concluído. "
                "Persistir cache V6 e executar "
                "novo lote."
            ),
        )

        log()

        log(
            "=" * 72
        )

        log(
            "B3 MARKET HISTORY V6 — "
            "LOTE CONCLUÍDO"
        )

        log(
            "=" * 72
        )

        log(
            "SPRE total:",
            spre_stats["files"],
        )

        log(
            "SPRE prontos:",
            spre_stats["ready"],
        )

        log(
            "SPRE pendentes:",
            spre_stats["pending"],
        )

        log(
            "SPRE processados nesta execução:",
            spre_stats["processed"],
        )

        log()

        log(
            "BUILD COMPLETE = false"
        )

        log(
            "Próxima ação:"
        )

        log(
            "Persistir cache market_history_v6 "
            "e continuar em nova execução."
        )

        log(
            "=" * 72
        )

        return {
            "complete": False,
            "phase": "SPRE_PARTITIONS",
            "years_loaded": years_loaded,
            "cotahist": cotahist_stats,
            "spre": spre_stats,
            "failures": failures,
        }

    # ========================================================
    # Proteção:
    # se alguma partição falhou, não publica snapshot parcial.
    # ========================================================

    if failures:

        write_build_status(
            complete=False,
            phase="SPRE_FAILURE",
            total_spre=spre_stats["files"],
            ready_spre=spre_stats["ready"],
            pending_spre=spre_stats["pending"],
            processed_now=spre_stats["processed"],
            message=(
                "Existem falhas SPRE. "
                "Snapshot final não publicado."
            ),
        )

        raise DataInsufficientError(
            "Existem falhas SPRE. "
            "Publicação final bloqueada."
        )

    # ========================================================
    # 4. CONSOLIDATION
    # ========================================================

    log(
        "\n[4/5] Consolidação única..."
    )

    log(
        "Consolidando COTAHIST..."
    )

    market = consolidate_cotahist(
        state
    )

    log(
        "  ✓ Registros COTAHIST:",
        len(market),
    )

    log(
        "Consolidando SPRE..."
    )

    spre = consolidate_spre(
        state
    )

    log(
        "  ✓ Registros SPRE:",
        len(spre),
    )

    # ========================================================
    # 5. AUDIT + PUBLICATION
    # ========================================================

    log(
        "\n[5/5] Auditoria e publicação..."
    )

    audit = audit_market_history(
        market,
        spre,
    )

    publish_outputs(
        market,
        spre,
    )

    save_state(state)

    manifest = build_manifest(
        audit=audit,
        cotahist_stats=cotahist_stats,
        spre_stats=spre_stats,
        failures=failures,
    )

    write_json_atomic(
        manifest,
        MANIFEST_FILE,
    )

    write_build_status(
        complete=True,
        phase="COMPLETE",
        total_spre=spre_stats["files"],
        ready_spre=spre_stats["ready"],
        pending_spre=0,
        processed_now=spre_stats["processed"],
        message=(
            "Market history consolidado, "
            "auditado e publicado."
        ),
    )

    # ========================================================
    # FINAL
    # ========================================================

    log(
        "\n"
        + "=" * 72
    )

    log(
        "B3 MARKET HISTORY — OK"
    )

    log(
        "=" * 72
    )

    log(
        "COTAHIST primeira data:",
        audit[
            "historical_first_date"
        ],
    )

    log(
        "COTAHIST última data:",
        audit[
            "historical_latest_date"
        ],
    )

    log(
        "SPRE primeira data:",
        audit[
            "spre_first_date"
        ],
    )

    log(
        "SPRE última data:",
        audit[
            "spre_latest_date"
        ],
    )

    log(
        "Registros liquidez:",
        audit[
            "liquidity_rows"
        ],
    )

    log(
        "Tickers liquidez:",
        audit[
            "liquidity_tickers"
        ],
    )

    log(
        "Registros SPRE:",
        audit[
            "spre_rows"
        ],
    )

    log(
        "Tickers SPRE:",
        audit[
            "spre_tickers"
        ],
    )

    log()

    log(
        "COTAHIST processados nesta execução:",
        cotahist_stats[
            "processed"
        ],
    )

    log(
        "SPRE processados nesta execução:",
        spre_stats[
            "processed"
        ],
    )

    log(
        "COTAHIST reaproveitados:",
        cotahist_stats[
            "unchanged"
        ],
    )

    log(
        "SPRE prontos:",
        spre_stats[
            "ready"
        ],
    )

    log()

    log(
        "ATENÇÃO:"
    )

    log(
        "BVBG.186.01 não fornece VOLTOT."
    )

    log(
        "RglrTxsQty NÃO foi convertido "
        "em volume financeiro."
    )

    log(
        "Metodologia de liquidez preservada."
    )

    log()

    log(
        "Saída liquidez:",
        OUTPUT_FILE,
    )

    log(
        "Saída preços SPRE:",
        SPRE_PRICE_FILE,
    )

    log(
        "Cache particionado V6:",
        CACHE_ROOT,
    )

    log()

    log(
        "BUILD COMPLETE = true"
    )

    log(
        "=" * 72
    )

    return {
        "complete": True,

        "market_history":
            market,

        "spre_prices":
            spre,

        "audit":
            audit,

        "incremental": {
            "cotahist":
                cotahist_stats,

            "spre":
                spre_stats,
        },
    }


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        result = build_b3_market_history()

        if (
            isinstance(result, dict)
            and
            not result.get(
                "complete",
                True,
            )
        ):

            #
            # IMPORTANTE:
            #
            # Retorna 0 propositalmente.
            #
            # O lote terminou corretamente.
            # O workflow será responsável por:
            #
            # 1. salvar o cache V6;
            # 2. verificar build_status.json;
            # 3. interromper as etapas posteriores enquanto
            #    complete == false.
            #
            return 0

        return 0

    except DataInsufficientError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            exc,
            file=sys.stderr,
            flush=True,
        )

        return 3

    except Exception as exc:

        print(
            "\nERROR:",
            repr(exc),
            file=sys.stderr,
            flush=True,
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
