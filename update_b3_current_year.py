from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import zipfile

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)

from io import BytesIO
from pathlib import Path

import requests


# ============================================================
# B3 INVESTMENT ENGINE
# LIVE B3 CURRENT YEAR DATA V3.0
# BATCHED + INCREMENTAL + RECOVERABLE BOOTSTRAP
# ============================================================
#
# Fonte oficial:
# B3 — Pesquisa por Pregão
# BVBG.186.01 — Simplified Price Report - Equities
#
# Padrão:
# SPRE{YYMMDD}.zip
#
# OBJETIVO
# ------------------------------------------------------------
# Evitar bootstrap janeiro -> hoje em uma única execução.
#
# PRIMEIRA CARGA:
# - processa no máximo BOOTSTRAP_BATCH_SIZE dias úteis;
# - grava cursor de progresso;
# - encerra normalmente;
# - workflow salva o diretório;
# - próxima chamada continua do cursor.
#
# CATCH-UP:
# - enquanto estiver muito atrasado, continua em lotes.
#
# MODO NORMAL:
# - quando alcança a região atual, verifica apenas pequena
#   janela de segurança.
#
# NÃO ALTERA:
# - Sector Engine
# - Quality Engine
# - Investability Engine
# - Valuation Engine
# - Technical Engine
#
# Metodologia:
# FROZEN_UNCHANGED
# ============================================================


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
B3_DIR = LIVE_DIR / "b3"

CURRENT_DIR = B3_DIR / "current_year"

MANIFEST_PATH = (
    B3_DIR
    / "b3_current_year_manifest.json"
)

BOOTSTRAP_STATE_PATH = (
    CURRENT_DIR
    / ".bootstrap_state.json"
)


# ============================================================
# DATA
# ============================================================


NOW_UTC = datetime.now(
    timezone.utc
)

CURRENT_YEAR = NOW_UTC.year

TODAY = NOW_UTC.date()

YEAR_START = date(
    CURRENT_YEAR,
    1,
    1,
)


# ============================================================
# REGRAS CONGELADAS
# ============================================================


HISTORY_RULE_YEARS = 10

MIN_DAILY_LIQUIDITY_BRL = (
    6_000_000
)


# ============================================================
# ENGENHARIA
# ============================================================


SAFETY_LOOKBACK_DAYS = 7

CATCHUP_THRESHOLD_DAYS = 14

BOOTSTRAP_BATCH_SIZE = int(
    os.environ.get(
        "B3_BOOTSTRAP_BATCH_SIZE",
        "25",
    )
)

if BOOTSTRAP_BATCH_SIZE < 1:
    BOOTSTRAP_BATCH_SIZE = 25


# ============================================================
# B3
# ============================================================


B3_PAGE_URL = (
    "https://www.b3.com.br/pt_br/"
    "market-data-e-indices/"
    "servicos-de-dados/"
    "market-data/historico/"
    "boletins-diarios/"
    "pesquisa-por-pregao/"
    "pesquisa-por-pregao/"
)

B3_DOWNLOAD_URL = (
    "https://www.b3.com.br/"
    "pesquisapregao/download"
)


# ============================================================
# REDE
# ============================================================


CONNECT_TIMEOUT = 5

READ_TIMEOUT = 30

REQUEST_DELAY_SECONDS = 0.10


# ============================================================
# EXCEÇÕES
# ============================================================


class B3CurrentYearError(
    RuntimeError
):
    pass


# ============================================================
# LOG
# ============================================================


def log(*args) -> None:

    print(
        *args,
        flush=True,
    )


# ============================================================
# DIRETÓRIOS
# ============================================================


def ensure_directories() -> None:

    CURRENT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    B3_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# JSON ATÔMICO
# ============================================================


def write_json_atomic(
    path: Path,
    payload: dict,
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
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


# ============================================================
# HASH
# ============================================================


def sha256_bytes(
    data: bytes,
) -> str:

    h = hashlib.sha256()

    h.update(data)

    return h.hexdigest()


# ============================================================
# ESCRITA ATÔMICA
# ============================================================


def atomic_write(
    path: Path,
    data: bytes,
) -> None:

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_bytes(data)

    tmp.replace(path)


# ============================================================
# NOMES B3
# ============================================================


def b3_filename(
    trading_date: date,
) -> str:

    return (
        "SPRE"
        + trading_date.strftime(
            "%y%m%d"
        )
        + ".zip"
    )


def local_filename(
    trading_date: date,
) -> str:

    return b3_filename(
        trading_date
    )


# ============================================================
# DATA PELO NOME
# ============================================================


def extract_date_from_filename(
    filename: str,
) -> date | None:

    name = (
        str(filename)
        .strip()
        .upper()
    )

    if not name.startswith("SPRE"):
        return None

    digits = name[4:10]

    if len(digits) != 6:
        return None

    try:

        return datetime.strptime(
            digits,
            "%y%m%d",
        ).date()

    except ValueError:

        return None


# ============================================================
# VALIDAÇÃO ZIP
# ============================================================


def validate_b3_zip_bytes(
    data: bytes,
) -> tuple[
    bool,
    list[str],
]:

    if len(data) <= 22:

        return (
            False,
            [],
        )

    bio = BytesIO(data)

    if not zipfile.is_zipfile(
        bio
    ):

        return (
            False,
            [],
        )

    try:

        with zipfile.ZipFile(
            bio
        ) as z:

            names = [
                name
                for name
                in z.namelist()
                if name
            ]

            if not names:

                return (
                    False,
                    [],
                )

            bad = z.testzip()

            if bad is not None:

                return (
                    False,
                    names,
                )

            return (
                True,
                names,
            )

    except zipfile.BadZipFile:

        return (
            False,
            [],
        )


def validate_local_file(
    path: Path,
) -> tuple[
    bool,
    list[str],
]:

    if not path.exists():

        return (
            False,
            [],
        )

    if path.stat().st_size <= 22:

        return (
            False,
            [],
        )

    try:

        if not zipfile.is_zipfile(
            path
        ):

            return (
                False,
                [],
            )

        with zipfile.ZipFile(
            path,
            "r",
        ) as z:

            names = [
                name
                for name
                in z.namelist()
                if name
            ]

            if not names:

                return (
                    False,
                    [],
                )

            bad = z.testzip()

            if bad is not None:

                return (
                    False,
                    names,
                )

            return (
                True,
                names,
            )

    except Exception:

        return (
            False,
            [],
        )


# ============================================================
# SESSÃO B3
# ============================================================


def create_b3_session() -> requests.Session:

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "pt-BR,pt;q=0.9,en;q=0.8"
            ),
        }
    )

    response = session.get(
        B3_PAGE_URL,
        timeout=(
            CONNECT_TIMEOUT,
            READ_TIMEOUT,
        ),
    )

    response.raise_for_status()

    return session


# ============================================================
# DOWNLOAD DE UM DIA
# ============================================================


def download_trading_day(
    session: requests.Session,
    trading_date: date,
) -> dict:

    filename = b3_filename(
        trading_date
    )

    local_path = (
        CURRENT_DIR
        / local_filename(
            trading_date
        )
    )

    local_valid, internal_names = (
        validate_local_file(
            local_path
        )
    )

    if local_valid:

        return {
            "date":
                trading_date.isoformat(),

            "filename":
                filename,

            "status":
                "LOCAL_VALID",

            "size_bytes":
                int(
                    local_path.stat().st_size
                ),

            "internal_files":
                internal_names,

            "path":
                str(
                    local_path.relative_to(
                        ROOT
                    )
                ),
        }

    if local_path.exists():
        local_path.unlink()

    try:

        response = session.get(
            B3_DOWNLOAD_URL,
            params={
                "filelist":
                    filename
            },
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
        )

    except requests.RequestException as exc:

        return {
            "date":
                trading_date.isoformat(),

            "filename":
                filename,

            "status":
                "NETWORK_ERROR",

            "error":
                repr(exc),
        }

    if response.status_code != 200:

        return {
            "date":
                trading_date.isoformat(),

            "filename":
                filename,

            "status":
                (
                    f"HTTP_"
                    f"{response.status_code}"
                ),

            "size_bytes":
                len(
                    response.content
                ),
        }

    data = response.content

    valid, internal_names = (
        validate_b3_zip_bytes(
            data
        )
    )

    if not valid:

        return {
            "date":
                trading_date.isoformat(),

            "filename":
                filename,

            "status":
                "NOT_AVAILABLE",

            "size_bytes":
                len(data),
        }

    atomic_write(
        local_path,
        data,
    )

    return {
        "date":
            trading_date.isoformat(),

        "filename":
            filename,

        "status":
            "DOWNLOADED",

        "size_bytes":
            len(data),

        "sha256":
            sha256_bytes(
                data
            ),

        "internal_files":
            internal_names,

        "path":
            str(
                local_path.relative_to(
                    ROOT
                )
            ),
    }


# ============================================================
# INVENTÁRIO LOCAL
# ============================================================


def inventory_local_files() -> list[dict]:

    files: list[dict] = []

    paths = sorted(
        list(
            CURRENT_DIR.glob(
                "SPRE*.zip"
            )
        )
        +
        list(
            CURRENT_DIR.glob(
                "SPRE*.ZIP"
            )
        )
    )

    seen = set()

    for path in paths:

        resolved = str(
            path.resolve()
        )

        if resolved in seen:
            continue

        seen.add(resolved)

        valid, internal = (
            validate_local_file(
                path
            )
        )

        if not valid:
            continue

        trading_date = (
            extract_date_from_filename(
                path.name
            )
        )

        if trading_date is None:
            continue

        if (
            trading_date.year
            != CURRENT_YEAR
        ):
            continue

        files.append(
            {
                "filename":
                    path.name,

                "date":
                    trading_date.isoformat(),

                "size_bytes":
                    int(
                        path.stat().st_size
                    ),

                "internal_files":
                    internal,

                "path":
                    str(
                        path.relative_to(
                            ROOT
                        )
                    ),
            }
        )

    return files


# ============================================================
# ÚLTIMA DATA LOCAL
# ============================================================


def latest_local_date(
    files: list[dict],
) -> date | None:

    dates: list[date] = []

    for item in files:

        d = extract_date_from_filename(
            item["filename"]
        )

        if d is not None:
            dates.append(d)

    if not dates:
        return None

    return max(dates)


# ============================================================
# BOOTSTRAP STATE
# ============================================================


def load_bootstrap_state() -> dict:

    if not BOOTSTRAP_STATE_PATH.exists():

        return {
            "year":
                CURRENT_YEAR,

            "last_checked_date":
                None,

            "complete":
                False,
        }

    try:

        payload = json.loads(
            BOOTSTRAP_STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return {
            "year":
                CURRENT_YEAR,

            "last_checked_date":
                None,

            "complete":
                False,
        }

    if (
        payload.get("year")
        != CURRENT_YEAR
    ):

        return {
            "year":
                CURRENT_YEAR,

            "last_checked_date":
                None,

            "complete":
                False,
        }

    return {
        "year":
            CURRENT_YEAR,

        "last_checked_date":
            payload.get(
                "last_checked_date"
            ),

        "complete":
            bool(
                payload.get(
                    "complete",
                    False,
                )
            ),
    }


def save_bootstrap_state(
    *,
    last_checked_date: date | None,
    complete: bool,
) -> None:

    payload = {
        "year":
            CURRENT_YEAR,

        "updated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "last_checked_date":
            (
                last_checked_date.isoformat()
                if last_checked_date
                else None
            ),

        "complete":
            bool(complete),
    }

    write_json_atomic(
        BOOTSTRAP_STATE_PATH,
        payload,
    )


# ============================================================
# DIAS ÚTEIS
# ============================================================


def weekdays_between(
    start: date,
    end: date,
) -> list[date]:

    if start > end:
        return []

    result: list[date] = []

    current = start

    while current <= end:

        if current.weekday() < 5:
            result.append(current)

        current += timedelta(
            days=1
        )

    return result


# ============================================================
# PLANO DE ATUALIZAÇÃO
# ============================================================


def build_update_plan(
    latest_local: date | None,
) -> tuple[
    str,
    list[date],
    bool,
]:

    """
    Retorna:

    mode:
        BOOTSTRAP
        CATCHUP
        INCREMENTAL

    dates:
        datas que ESTA chamada deve verificar.

    batch_complete:
        indica se esta chamada já alcança a região atual.

    O cursor usa a última DATA VERIFICADA, e não somente
    o último pregão encontrado. Isso evita ficar preso em
    feriados ou datas sem arquivo.
    """

    state = load_bootstrap_state()

    last_checked_raw = (
        state.get(
            "last_checked_date"
        )
    )

    last_checked: date | None = None

    if last_checked_raw:

        try:

            last_checked = date.fromisoformat(
                str(
                    last_checked_raw
                )
            )

        except ValueError:
            last_checked = None

    # ========================================================
    # ESTADO JÁ COMPLETO
    # ========================================================

    if state.get("complete"):

        if latest_local is None:

            # Cache inconsistente:
            # cursor diz completo, mas não existem arquivos.
            # Reinicia de forma segura.

            save_bootstrap_state(
                last_checked_date=None,
                complete=False,
            )

        else:

            start = (
                latest_local
                - timedelta(
                    days=SAFETY_LOOKBACK_DAYS
                )
            )

            if start < YEAR_START:
                start = YEAR_START

            dates = weekdays_between(
                start,
                TODAY,
            )

            return (
                "INCREMENTAL",
                dates,
                True,
            )

    # ========================================================
    # BOOTSTRAP / CATCH-UP
    # ========================================================

    if last_checked is None:

        start = YEAR_START

        mode = "BOOTSTRAP"

    else:

        start = (
            last_checked
            + timedelta(
                days=1
            )
        )

        mode = "CATCHUP"

    all_pending = weekdays_between(
        start,
        TODAY,
    )

    if not all_pending:

        save_bootstrap_state(
            last_checked_date=TODAY,
            complete=True,
        )

        if latest_local is None:

            return (
                "BOOTSTRAP",
                [],
                True,
            )

        incremental_start = (
            latest_local
            - timedelta(
                days=SAFETY_LOOKBACK_DAYS
            )
        )

        if incremental_start < YEAR_START:
            incremental_start = YEAR_START

        return (
            "INCREMENTAL",
            weekdays_between(
                incremental_start,
                TODAY,
            ),
            True,
        )

    dates = all_pending[
        :BOOTSTRAP_BATCH_SIZE
    ]

    batch_complete = (
        len(dates)
        ==
        len(all_pending)
    )

    return (
        mode,
        dates,
        batch_complete,
    )


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    *,
    status: str,
    mode: str,
    results: list[dict],
    valid_files: list[dict],
    latest_available_date: str | None,
    latest_before_update: str | None,
    bootstrap_complete: bool,
    batch_last_checked: str | None,
) -> None:

    downloaded = sum(
        x.get("status")
        == "DOWNLOADED"
        for x in results
    )

    reused = sum(
        x.get("status")
        == "LOCAL_VALID"
        for x in results
    )

    unavailable = sum(
        x.get("status")
        == "NOT_AVAILABLE"
        for x in results
    )

    network_errors = sum(
        x.get("status")
        == "NETWORK_ERROR"
        for x in results
    )

    http_errors = sum(
        str(
            x.get(
                "status",
                "",
            )
        ).startswith(
            "HTTP_"
        )
        for x in results
    )

    manifest = {
        "engine":
            "B3_INVESTMENT_ENGINE",

        "data_layer":
            (
                "LIVE_B3_CURRENT_YEAR_"
                "V3_BATCHED_INCREMENTAL"
            ),

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "reference_year":
            CURRENT_YEAR,

        "source": {
            "institution":
                "B3",

            "dataset":
                (
                    "BVBG.186.01 - "
                    "Simplified Price Report - Equities"
                ),

            "filename_pattern":
                "SPRE{YYMMDD}.zip",

            "official":
                True,

            "endpoint_validated":
                True,
        },

        "status":
            status,

        "mode":
            mode,

        "latest_before_update":
            latest_before_update,

        "latest_available_date":
            latest_available_date,

        "incremental_update": {
            "enabled":
                True,

            "bootstrap_batch_size":
                BOOTSTRAP_BATCH_SIZE,

            "bootstrap_complete":
                bootstrap_complete,

            "batch_last_checked":
                batch_last_checked,

            "safety_lookback_days":
                SAFETY_LOOKBACK_DAYS,

            "full_year_rescan_each_run":
                False,
        },

        "statistics": {
            "candidate_dates_checked":
                len(results),

            "downloaded":
                int(downloaded),

            "reused_local":
                int(reused),

            "not_available":
                int(unavailable),

            "network_errors":
                int(network_errors),

            "http_errors":
                int(http_errors),

            "valid_local_files":
                len(valid_files),
        },

        "results":
            results,

        "valid_files":
            valid_files,

        "methodology": {
            "status":
                "FROZEN_UNCHANGED",

            "history_rule_years":
                HISTORY_RULE_YEARS,

            "minimum_daily_liquidity_brl":
                MIN_DAILY_LIQUIDITY_BRL,

            "sector_engine_altered":
                False,

            "quality_engine_altered":
                False,

            "investability_engine_altered":
                False,

            "valuation_engine_altered":
                False,

            "technical_engine_altered":
                False,
        },
    }

    write_json_atomic(
        MANIFEST_PATH,
        manifest,
    )


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    ensure_directories()

    log(
        "=" * 72
    )

    log(
        "B3 LIVE DATA — "
        "ANO CORRENTE V3.0 "
        "BATCHED INCREMENTAL"
    )

    log(
        "=" * 72
    )

    log(
        "Fonte:",
        (
            "B3 BVBG.186.01 — "
            "Simplified Price Report - Equities"
        ),
    )

    log(
        "Ano:",
        CURRENT_YEAR,
    )

    log(
        "Padrão:",
        "SPRE{YYMMDD}.zip",
    )

    log(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    log(
        "Bootstrap batch:",
        BOOTSTRAP_BATCH_SIZE,
        "dias úteis",
    )

    log(
        "=" * 72
    )

    # ========================================================
    # INVENTÁRIO
    # ========================================================

    log(
        "\n[1/4] Inventário local..."
    )

    valid_before = (
        inventory_local_files()
    )

    latest_before = (
        latest_local_date(
            valid_before
        )
    )

    log(
        "Arquivos SPRE locais válidos:",
        len(valid_before),
    )

    log(
        "Último pregão local:",
        (
            latest_before.isoformat()
            if latest_before
            else "NENHUM"
        ),
    )

    # ========================================================
    # PLANO
    # ========================================================

    log(
        "\n[2/4] Determinando lote..."
    )

    (
        mode,
        dates,
        batch_reaches_current,
    ) = build_update_plan(
        latest_before
    )

    log(
        "Modo:",
        mode,
    )

    log(
        "Datas nesta chamada:",
        len(dates),
    )

    if dates:

        log(
            "Período do lote:",
            dates[0].isoformat(),
            "→",
            dates[-1].isoformat(),
        )

    else:

        log(
            "Nenhuma data pendente."
        )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    log(
        "\n[3/4] Atualização oficial B3..."
    )

    results: list[dict] = []

    last_successfully_checked: date | None = None

    if dates:

        try:

            log(
                "Criando sessão oficial B3..."
            )

            session = (
                create_b3_session()
            )

            log(
                "✓ Sessão B3 criada"
            )

        except Exception as exc:

            raise B3CurrentYearError(
                "Não foi possível criar "
                "sessão com a B3."
            ) from exc

        total = len(dates)

        for index, trading_date in enumerate(
            dates,
            start=1,
        ):

            filename = b3_filename(
                trading_date
            )

            log(
                f"[{index}/{total}] "
                f"{trading_date.isoformat()} "
                f"— {filename}"
            )

            result = download_trading_day(
                session,
                trading_date,
            )

            results.append(result)

            result_status = result.get(
                "status",
                "UNKNOWN",
            )

            # Somente avançamos o cursor quando a data
            # foi efetivamente resolvida.
            #
            # NETWORK_ERROR/HTTP_* não avançam o cursor
            # além da falha, para que a próxima chamada
            # possa tentar novamente.

            resolved = (
                result_status
                in {
                    "DOWNLOADED",
                    "LOCAL_VALID",
                    "NOT_AVAILABLE",
                }
            )

            if resolved:

                last_successfully_checked = (
                    trading_date
                )

            if (
                result_status
                == "DOWNLOADED"
            ):

                mb = (
                    result.get(
                        "size_bytes",
                        0,
                    )
                    / 1024
                    / 1024
                )

                log(
                    f"   ✓ BAIXADO "
                    f"({mb:.2f} MB)"
                )

            elif (
                result_status
                == "LOCAL_VALID"
            ):

                log(
                    "   ✓ LOCAL VÁLIDO"
                )

            elif (
                result_status
                == "NOT_AVAILABLE"
            ):

                log(
                    "   - SEM PREGÃO/"
                    "INDISPONÍVEL"
                )

            elif (
                result_status
                == "NETWORK_ERROR"
            ):

                log(
                    "   ! ERRO DE REDE"
                )

                # Interrompe o lote aqui.
                # Não pulamos datas após erro de rede.

                break

            elif str(
                result_status
            ).startswith(
                "HTTP_"
            ):

                log(
                    f"   ! {result_status}"
                )

                break

            else:

                log(
                    f"   ! {result_status}"
                )

                break

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    # ========================================================
    # ATUALIZA CURSOR
    # ========================================================

    previous_state = (
        load_bootstrap_state()
    )

    previous_last_checked = None

    previous_raw = (
        previous_state.get(
            "last_checked_date"
        )
    )

    if previous_raw:

        try:

            previous_last_checked = (
                date.fromisoformat(
                    str(previous_raw)
                )
            )

        except ValueError:
            previous_last_checked = None

    cursor_date = (
        last_successfully_checked
        or
        previous_last_checked
    )

    # Consideramos bootstrap completo somente quando:
    # - este lote deveria alcançar a região atual;
    # - todas as datas planejadas foram resolvidas;
    # - não houve erro interrompendo o lote.

    all_planned_resolved = (
        len(results)
        == len(dates)
        and
        all(
            item.get("status")
            in {
                "DOWNLOADED",
                "LOCAL_VALID",
                "NOT_AVAILABLE",
            }
            for item in results
        )
    )

    bootstrap_complete = bool(
        (
            mode
            in {
                "BOOTSTRAP",
                "CATCHUP",
            }
        )
        and
        batch_reaches_current
        and
        all_planned_resolved
    )

    if mode == "INCREMENTAL":

        bootstrap_complete = True

    if (
        mode
        in {
            "BOOTSTRAP",
            "CATCHUP",
        }
    ):

        save_bootstrap_state(
            last_checked_date=cursor_date,
            complete=bootstrap_complete,
        )

    elif mode == "INCREMENTAL":

        save_bootstrap_state(
            last_checked_date=TODAY,
            complete=True,
        )

    # ========================================================
    # AUDITORIA FINAL
    # ========================================================

    log(
        "\n[4/4] Auditoria final..."
    )

    valid_files = (
        inventory_local_files()
    )

    latest = latest_local_date(
        valid_files
    )

    latest_iso = (
        latest.isoformat()
        if latest
        else None
    )

    latest_before_iso = (
        latest_before.isoformat()
        if latest_before
        else None
    )

    # Durante bootstrap parcial isso NÃO é erro.
    # O objetivo é permitir salvar o cache e continuar.

    if (
        mode
        in {
            "BOOTSTRAP",
            "CATCHUP",
        }
        and
        not bootstrap_complete
    ):

        status = (
            "BOOTSTRAP_IN_PROGRESS"
        )

    elif latest is None:

        status = (
            "DATA_INSUFFICIENT"
        )

    else:

        status = (
            "CURRENT_YEAR_READY"
        )

    write_manifest(
        status=status,
        mode=mode,
        results=results,
        valid_files=valid_files,
        latest_available_date=latest_iso,
        latest_before_update=latest_before_iso,
        bootstrap_complete=bootstrap_complete,
        batch_last_checked=(
            cursor_date.isoformat()
            if cursor_date
            else None
        ),
    )

    downloaded = sum(
        x.get("status")
        == "DOWNLOADED"
        for x in results
    )

    reused = sum(
        x.get("status")
        == "LOCAL_VALID"
        for x in results
    )

    unavailable = sum(
        x.get("status")
        == "NOT_AVAILABLE"
        for x in results
    )

    network_errors = sum(
        x.get("status")
        == "NETWORK_ERROR"
        for x in results
    )

    log()

    log(
        "=" * 72
    )

    log(
        "RESULTADO — B3 ANO CORRENTE"
    )

    log(
        "=" * 72
    )

    log(
        "Status:",
        status,
    )

    log(
        "Modo:",
        mode,
    )

    log(
        "Arquivos válidos:",
        len(valid_files),
    )

    log(
        "Datas verificadas agora:",
        len(results),
    )

    log(
        "Baixados agora:",
        downloaded,
    )

    log(
        "Reutilizados:",
        reused,
    )

    log(
        "Sem pregão/indisponíveis:",
        unavailable,
    )

    log(
        "Erros de rede:",
        network_errors,
    )

    log(
        "Último pregão antes:",
        latest_before_iso,
    )

    log(
        "Último pregão disponível:",
        latest_iso,
    )

    log(
        "Cursor:",
        (
            cursor_date.isoformat()
            if cursor_date
            else None
        ),
    )

    log(
        "Bootstrap completo:",
        bootstrap_complete,
    )

    log(
        "Manifest:",
        MANIFEST_PATH,
    )

    log()

    log(
        "Sector Engine alterado: NÃO"
    )

    log(
        "Quality Engine alterado: NÃO"
    )

    log(
        "Investability Engine alterado: NÃO"
    )

    log(
        "Valuation Engine alterado: NÃO"
    )

    log(
        "Technical Engine alterado: NÃO"
    )

    log(
        "=" * 72
    )

    if status == "DATA_INSUFFICIENT":

        log(
            "✗ DATA_INSUFFICIENT"
        )

        return 2

    if status == "BOOTSTRAP_IN_PROGRESS":

        log(
            "✓ LOTE CONCLUÍDO."
        )

        log(
            "Bootstrap ainda não terminou."
        )

        log(
            "O workflow deve salvar o cache "
            "antes do próximo lote."
        )

        return 0

    if network_errors:

        log(
            "⚠ Camada disponível, mas ocorreram "
            "erros de rede."
        )

    log(
        "✓ CAMADA B3 DO ANO CORRENTE PRONTA"
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================


if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        log(
            "\nExecução interrompida."
        )

        sys.exit(130)

    except B3CurrentYearError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            str(exc),
            file=sys.stderr,
            flush=True,
        )

        sys.exit(2)

    except Exception as exc:

        print(
            "\nERRO:",
            repr(exc),
            file=sys.stderr,
            flush=True,
        )

        sys.exit(1)
