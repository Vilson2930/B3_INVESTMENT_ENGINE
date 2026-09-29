# ============================================================
# B3 INVESTMENT ENGINE
# BUILD B3 MARKET HISTORY — V4 INCREMENTAL SNAPSHOT
#
# OBJETIVO
# ------------------------------------------------------------
# Construir e manter incrementalmente:
#
# 1. market_history_live.csv
#    - histórico oficial de liquidez;
#    - fonte: B3 COTAHIST;
#    - VOLTOT oficial.
#
# 2. spre_prices_live.csv
#    - preços oficiais do ano corrente;
#    - fonte: B3 BVBG.186.01;
#    - NÃO transforma RglrTxsQty em VOLTOT.
#
# ARQUITETURA V4
# ------------------------------------------------------------
# - snapshots consolidados persistentes;
# - inventário de fontes já incorporadas;
# - somente arquivo novo/alterado é processado;
# - execução interrompida não perde o progresso já salvo;
# - COTAHIST histórico não é reconstruído sem necessidade;
# - SPRE antigo não é reaberto sem necessidade;
# - dados novos entram a cada execução.
#
# METODOLOGIA
# ------------------------------------------------------------
# NÃO altera:
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
# ============================================================

from __future__ import annotations

import hashlib
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


# ============================================================
# ESTADO INCREMENTAL
# ============================================================

STATE_DIR = (
    B3_DIR / "cache" / "market_history_v4"
)

STATE_FILE = (
    STATE_DIR / "state.json"
)

MARKET_SNAPSHOT_FILE = (
    STATE_DIR / "market_history_snapshot.csv"
)

SPRE_SNAPSHOT_FILE = (
    STATE_DIR / "spre_prices_snapshot.csv"
)


# ============================================================
# CONSTANTS
# ============================================================

CURRENT_YEAR = datetime.now(
    timezone.utc
).year

VALID_MARKET_TYPE = "010"

METHODOLOGY_VERSION = (
    "B3_MARKET_HISTORY_V4_INCREMENTAL_SNAPSHOT"
)

STATE_VERSION = 1

MINIMUM_HISTORY_YEARS = 10

MINIMUM_DAILY_LIQUIDITY_BRL = (
    6_000_000
)


# ============================================================
# DIRETÓRIOS
# ============================================================

B3_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

STATE_DIR.mkdir(
    parents=True,
    exist_ok=True,
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

    tmp.replace(
        path
    )


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

    tmp.replace(
        path
    )


def normalize_ticker(
    value,
):

    if pd.isna(
        value
    ):

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
# IDENTIDADE ESTÁVEL DA FONTE
# ============================================================
#
# Não usa mtime.
#
# GitHub runner pode recriar um arquivo com nova data de
# modificação mesmo quando o conteúdo oficial é o mesmo.
#
# Identidade:
# - nome;
# - tamanho;
# - hash SHA-256.
#
# ============================================================

def sha256_file(
    path: Path,
) -> str:

    h = hashlib.sha256()

    with path.open(
        "rb"
    ) as stream:

        for chunk in iter(
            lambda: stream.read(
                1024 * 1024
            ),
            b"",
        ):

            h.update(
                chunk
            )

    return h.hexdigest()


def source_identity(
    path: Path,
) -> dict:

    return {
        "filename":
            path.name,

        "size_bytes":
            int(
                path.stat().st_size
            ),

        "sha256":
            sha256_file(
                path
            ),
    }


def same_identity(
    old: dict | None,
    new: dict,
) -> bool:

    if not old:

        return False

    return (
        old.get(
            "filename"
        )
        ==
        new.get(
            "filename"
        )
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
        old.get(
            "sha256"
        )
        ==
        new.get(
            "sha256"
        )
    )


# ============================================================
# ESTADO
# ============================================================

def empty_state() -> dict:

    return {
        "state_version":
            STATE_VERSION,

        "generated_at_utc":
            utc_now_iso(),

        "cotahist":
            {},

        "spre":
            {},
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

    if (
        state.get(
            "state_version"
        )
        !=
        STATE_VERSION
    ):

        return empty_state()

    if not isinstance(
        state.get(
            "cotahist"
        ),
        dict,
    ):

        state["cotahist"] = {}

    if not isinstance(
        state.get(
            "spre"
        ),
        dict,
    ):

        state["spre"] = {}

    return state


def save_state(
    state: dict,
) -> None:

    state["generated_at_utc"] = (
        utc_now_iso()
    )

    write_json_atomic(
        state,
        STATE_FILE,
    )


# ============================================================
# SNAPSHOT — MARKET HISTORY
# ============================================================

def empty_market_snapshot() -> pd.DataFrame:

    return pd.DataFrame(
        columns=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )


def load_market_snapshot() -> pd.DataFrame:

    candidate = None

    if MARKET_SNAPSHOT_FILE.exists():

        candidate = (
            MARKET_SNAPSHOT_FILE
        )

    elif OUTPUT_FILE.exists():

        candidate = (
            OUTPUT_FILE
        )

    if candidate is None:

        return empty_market_snapshot()

    try:

        df = pd.read_csv(
            candidate,
            low_memory=False,
        )

    except Exception:

        return empty_market_snapshot()

    required = {
        "TICKER",
        "DATA",
        "VOLTOT",
    }

    if not required.issubset(
        set(
            df.columns
        )
    ):

        return empty_market_snapshot()

    df = df[
        [
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    ].copy()

    df["TICKER"] = (
        df["TICKER"]
        .map(
            normalize_ticker
        )
    )

    df["DATA"] = pd.to_datetime(
        df["DATA"],
        errors="coerce",
    )

    df["VOLTOT"] = pd.to_numeric(
        df["VOLTOT"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    df = df[
        df["VOLTOT"] >= 0
    ].copy()

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


# ============================================================
# SNAPSHOT — SPRE
# ============================================================

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


def empty_spre_snapshot() -> pd.DataFrame:

    return pd.DataFrame(
        columns=SPRE_COLUMNS
    )


def load_spre_snapshot() -> pd.DataFrame:

    candidate = None

    if SPRE_SNAPSHOT_FILE.exists():

        candidate = (
            SPRE_SNAPSHOT_FILE
        )

    elif SPRE_PRICE_FILE.exists():

        candidate = (
            SPRE_PRICE_FILE
        )

    if candidate is None:

        return empty_spre_snapshot()

    try:

        df = pd.read_csv(
            candidate,
            low_memory=False,
        )

    except Exception:

        return empty_spre_snapshot()

    required = {
        "TICKER",
        "DATA",
    }

    if not required.issubset(
        set(
            df.columns
        )
    ):

        return empty_spre_snapshot()

    for column in SPRE_COLUMNS:

        if column not in df.columns:

            df[column] = pd.NA

    df = df[
        SPRE_COLUMNS
    ].copy()

    df["TICKER"] = (
        df["TICKER"]
        .map(
            normalize_ticker
        )
    )

    df["DATA"] = pd.to_datetime(
        df["DATA"],
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

        df[column] = pd.to_numeric(
            df[column],
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
        .reset_index(
            drop=True
        )
    )


# ============================================================
# COTAHIST — PARSER
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

    vol_raw = (
        line[170:188]
        .strip()
    )

    try:

        voltot = (
            int(
                vol_raw
            )
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
            float(
                voltot
            ),
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

                        records.append(
                            row
                        )

    except zipfile.BadZipFile as exc:

        raise DataInsufficientError(
            "COTAHIST ZIP inválido: "
            f"{path}"
        ) from exc

    if not records:

        return empty_market_snapshot()

    df = pd.DataFrame(
        records
    )

    df["TICKER"] = (
        df["TICKER"]
        .map(
            normalize_ticker
        )
    )

    df["DATA"] = pd.to_datetime(
        df["DATA"],
        errors="coerce",
    )

    df["VOLTOT"] = pd.to_numeric(
        df["VOLTOT"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ]
    )

    df = df[
        df["VOLTOT"] >= 0
    ].copy()

    # Consolida eventual duplicidade do mesmo ticker/dia
    # dentro do arquivo anual.

    df = (
        df
        .groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
            sort=False,
        )["VOLTOT"]
        .sum()
    )

    return df


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

            values[
                key
            ] = text

    return values


def parse_spre_xml(
    payload: bytes,
    filename_trade_date: pd.Timestamp,
) -> pd.DataFrame:

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

    date_code = match.group(
        1
    )

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
# LISTAGEM DE FONTES
# ============================================================

def list_cotahist_files() -> list[Path]:

    if not HISTORICAL_DIR.exists():

        raise DataInsufficientError(
            "Diretório COTAHIST não encontrado: "
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

    unique = []
    seen = set()

    for path in files:

        key = str(
            path.resolve()
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        unique.append(
            path
        )

    if not unique:

        raise DataInsufficientError(
            "Nenhum COTAHIST anual "
            "foi encontrado."
        )

    return unique


def list_spre_files() -> list[Path]:

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

    unique = []
    seen = set()

    for path in files:

        key = str(
            path.resolve()
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        unique.append(
            path
        )

    if not unique:

        raise DataInsufficientError(
            "Nenhum arquivo SPRE do "
            "ano corrente foi encontrado."
        )

    return unique


# ============================================================
# COTAHIST — INCREMENTAL
# ============================================================

def update_cotahist_snapshot(
    market: pd.DataFrame,
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

        years.append(
            year
        )

        print(
            f"  COTAHIST {index}/{len(files)} "
            f"- {path.name}"
        )

        identity = source_identity(
            path
        )

        old_identity = (
            state["cotahist"]
            .get(
                path.name
            )
        )

        if (
            same_identity(
                old_identity,
                identity,
            )
            and
            not market.empty
        ):

            print(
                "    ✓ JÁ INCORPORADO"
            )

            unchanged += 1

            continue

        print(
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

        # Se a fonte do mesmo ano mudou,
        # remove os registros daquele ano antes
        # de incorporar a nova versão.

        if not market.empty:

            market = market[
                market["DATA"].dt.year
                !=
                year
            ].copy()

        market = pd.concat(
            [
                market,
                year_df,
            ],
            ignore_index=True,
        )

        market = (
            market
            .groupby(
                [
                    "TICKER",
                    "DATA",
                ],
                as_index=False,
                sort=False,
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

        # ====================================================
        # CHECKPOINT IMEDIATO
        # ====================================================
        #
        # Se a execução for interrompida depois,
        # este ano não precisará ser processado novamente.
        # ====================================================

        write_csv_atomic(
            market,
            MARKET_SNAPSHOT_FILE,
        )

        state["cotahist"][
            path.name
        ] = identity

        save_state(
            state
        )

        processed += 1

        print(
            f"    ✓ INCORPORADO — "
            f"{len(year_df)} registros"
        )

    years = sorted(
        set(
            years
        )
    )

    return (
        market,
        years,
        {
            "files":
                len(
                    files
                ),

            "unchanged":
                unchanged,

            "processed":
                processed,
        },
    )


# ============================================================
# SPRE — INCREMENTAL
# ============================================================

def update_spre_snapshot(
    spre: pd.DataFrame,
    state: dict,
):

    files = list_spre_files()

    processed = 0
    unchanged = 0
    failures = []

    for index, path in enumerate(
        files,
        start=1,
    ):

        print(
            f"  SPRE {index}/{len(files)} "
            f"- {path.name}"
        )

        identity = source_identity(
            path
        )

        old_identity = (
            state["spre"]
            .get(
                path.name
            )
        )

        if (
            same_identity(
                old_identity,
                identity,
            )
            and
            not spre.empty
        ):

            print(
                "    ✓ JÁ INCORPORADO"
            )

            unchanged += 1

            continue

        try:

            print(
                "    PROCESSANDO..."
            )

            day_df = parse_spre_zip(
                path
            )

            if day_df.empty:

                raise DataInsufficientError(
                    "SPRE vazio."
                )

            trade_dates = (
                pd.to_datetime(
                    day_df["DATA"],
                    errors="coerce",
                )
                .dropna()
                .dt.normalize()
                .unique()
            )

            # Se o arquivo foi substituído,
            # remove apenas os dias presentes nele.

            if (
                not spre.empty
                and
                len(
                    trade_dates
                )
                > 0
            ):

                normalized_existing = (
                    pd.to_datetime(
                        spre["DATA"],
                        errors="coerce",
                    )
                    .dt.normalize()
                )

                spre = spre[
                    ~normalized_existing.isin(
                        trade_dates
                    )
                ].copy()

            spre = pd.concat(
                [
                    spre,
                    day_df,
                ],
                ignore_index=True,
            )

            spre["TICKER"] = (
                spre["TICKER"]
                .map(
                    normalize_ticker
                )
            )

            spre["DATA"] = pd.to_datetime(
                spre["DATA"],
                errors="coerce",
            )

            spre = spre.dropna(
                subset=[
                    "TICKER",
                    "DATA",
                ]
            )

            for column in SPRE_COLUMNS:

                if column not in spre.columns:

                    spre[column] = pd.NA

            spre = (
                spre[
                    SPRE_COLUMNS
                ]
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

            # =================================================
            # CHECKPOINT IMEDIATO
            # =================================================
            #
            # Cada SPRE concluído é persistido.
            #
            # Se GitHub interromper a execução no arquivo 110,
            # os 109 anteriores continuam incorporados.
            # =================================================

            write_csv_atomic(
                spre,
                SPRE_SNAPSHOT_FILE,
            )

            state["spre"][
                path.name
            ] = identity

            save_state(
                state
            )

            processed += 1

            print(
                f"    ✓ INCORPORADO — "
                f"{len(day_df)} registros"
            )

        except Exception as exc:

            failures.append(
                {
                    "file":
                        path.name,

                    "error":
                        str(
                            exc
                        ),
                }
            )

            print(
                "    ! FALHA:",
                str(
                    exc
                ),
            )

    return (
        spre,
        failures,
        {
            "files":
                len(
                    files
                ),

            "unchanged":
                unchanged,

            "processed":
                processed,
        },
    )


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

    market = market.copy()
    spre_prices = spre_prices.copy()

    market["DATA"] = pd.to_datetime(
        market["DATA"],
        errors="coerce",
    )

    spre_prices["DATA"] = pd.to_datetime(
        spre_prices["DATA"],
        errors="coerce",
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
# PUBLICAÇÃO DOS SNAPSHOTS
# ============================================================

def publish_outputs(
    market: pd.DataFrame,
    spre: pd.DataFrame,
) -> None:

    market_out = market[
        [
            "TICKER",
            "DATA",
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

    market_out = (
        market_out
        .dropna(
            subset=[
                "TICKER",
                "DATA",
                "VOLTOT",
            ]
        )
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

    spre_out = (
        spre_out
        .dropna(
            subset=[
                "TICKER",
                "DATA",
            ]
        )
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

    # Estado interno persistente

    write_csv_atomic(
        market_out,
        MARKET_SNAPSHOT_FILE,
    )

    write_csv_atomic(
        spre_out,
        SPRE_SNAPSHOT_FILE,
    )

    # Interfaces oficiais consumidas pelo restante do robô

    write_csv_atomic(
        market_out,
        OUTPUT_FILE,
    )

    write_csv_atomic(
        spre_out,
        SPRE_PRICE_FILE,
    )


# ============================================================
# BUILD
# ============================================================

def build_b3_market_history():

    print(
        "=" * 72
    )

    print(
        "B3 INVESTMENT ENGINE — "
        "BUILD MARKET HISTORY V4 "
        "INCREMENTAL"
    )

    print(
        "=" * 72
    )

    # ========================================================
    # ESTADO
    # ========================================================

    print(
        "\n[1/4] Carregando estado incremental..."
    )

    state = load_state()

    market = load_market_snapshot()

    spre = load_spre_snapshot()

    print(
        "Registros liquidez já persistidos:",
        len(
            market
        ),
    )

    print(
        "Registros SPRE já persistidos:",
        len(
            spre
        ),
    )

    print(
        "COTAHIST registrados no estado:",
        len(
            state["cotahist"]
        ),
    )

    print(
        "SPRE registrados no estado:",
        len(
            state["spre"]
        ),
    )

    # ========================================================
    # COTAHIST
    # ========================================================

    print(
        "\n[2/4] Atualização incremental COTAHIST..."
    )

    (
        market,
        years_loaded,
        cotahist_stats,
    ) = update_cotahist_snapshot(
        market,
        state,
    )

    print(
        "\nAnos disponíveis:",
        years_loaded,
    )

    print(
        "COTAHIST já incorporados:",
        cotahist_stats[
            "unchanged"
        ],
    )

    print(
        "COTAHIST processados agora:",
        cotahist_stats[
            "processed"
        ],
    )

    # ========================================================
    # SPRE
    # ========================================================

    print(
        "\n[3/4] Atualização incremental SPRE..."
    )

    (
        spre,
        failures,
        spre_stats,
    ) = update_spre_snapshot(
        spre,
        state,
    )

    print(
        "\nSPRE já incorporados:",
        spre_stats[
            "unchanged"
        ],
    )

    print(
        "SPRE processados agora:",
        spre_stats[
            "processed"
        ],
    )

    print(
        "Falhas SPRE:",
        len(
            failures
        ),
    )

    # ========================================================
    # AUDITORIA + PUBLICAÇÃO
    # ========================================================

    print(
        "\n[4/4] Auditoria e publicação..."
    )

    audit = audit_market_history(
        market,
        spre,
    )

    publish_outputs(
        market,
        spre,
    )

    save_state(
        state
    )

    # ========================================================
    # MANIFEST
    # ========================================================

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

        "architecture":
            "INCREMENTAL_PERSISTENT_SNAPSHOT",

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

        "state_file":
            str(
                STATE_FILE
            ),

        "market_snapshot":
            str(
                MARKET_SNAPSHOT_FILE
            ),

        "spre_snapshot":
            str(
                SPRE_SNAPSHOT_FILE
            ),

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

    # ========================================================
    # FINAL
    # ========================================================

    print(
        "\n"
        + "=" * 72
    )

    print(
        "B3 MARKET HISTORY — OK"
    )

    print(
        "=" * 72
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
        "SPRE primeira data:",
        audit[
            "spre_first_date"
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

    print()

    print(
        "COTAHIST processados nesta execução:",
        cotahist_stats[
            "processed"
        ],
    )

    print(
        "SPRE processados nesta execução:",
        spre_stats[
            "processed"
        ],
    )

    print(
        "COTAHIST reaproveitados:",
        cotahist_stats[
            "unchanged"
        ],
    )

    print(
        "SPRE reaproveitados:",
        spre_stats[
            "unchanged"
        ],
    )

    print()

    print(
        "ATENÇÃO:"
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

    print()

    print(
        "Saída liquidez:",
        OUTPUT_FILE,
    )

    print(
        "Saída preços SPRE:",
        SPRE_PRICE_FILE,
    )

    print(
        "Estado incremental:",
        STATE_FILE,
    )

    print(
        "=" * 72
    )

    return {
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
            repr(
                exc
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
