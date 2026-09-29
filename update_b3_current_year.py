from __future__ import annotations

import hashlib
import json
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
# LIVE B3 CURRENT YEAR DATA V2.0 — INCREMENTAL
#
# Fonte oficial:
# B3 — Pesquisa por Pregão
# BVBG.186.01 — Simplified Price Report - Equities
#
# Padrão oficial:
# SPRE{YYMMDD}.zip
#
# OBJETIVO
# ------------------------------------------------------------
# Atualizar o ano corrente da B3 sem consultar novamente
# todos os pregões desde janeiro em toda execução.
#
# ARQUITETURA
# ------------------------------------------------------------
# 1. Arquivos SPRE locais válidos são preservados.
#
# 2. Se ainda não existe nenhum SPRE local:
#       faz bootstrap do ano corrente.
#
# 3. Se já existe histórico local:
#       consulta somente:
#
#       último pregão local + 1 dia
#                   até
#       hoje
#
# 4. Uma pequena janela de segurança anterior ao último
#    pregão também pode ser verificada localmente, mas
#    arquivos válidos NÃO são baixados novamente.
#
# 5. Feriados não são inventados.
#    A própria B3 informa indisponibilidade.
#
# 6. Nenhuma metodologia do robô é alterada.
#
# NÃO altera:
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

CURRENT_DIR = (
    B3_DIR
    / "current_year"
)

MANIFEST_PATH = (
    B3_DIR
    / "b3_current_year_manifest.json"
)


# ============================================================
# DATA
# ============================================================


NOW_UTC = datetime.now(
    timezone.utc
)

CURRENT_YEAR = (
    NOW_UTC.year
)

TODAY = (
    NOW_UTC.date()
)


# ============================================================
# REGRAS CONGELADAS
# ============================================================


HISTORY_RULE_YEARS = 10

MIN_DAILY_LIQUIDITY_BRL = (
    6_000_000
)


# ============================================================
# ENGENHARIA INCREMENTAL
# ============================================================


# Pequena janela de segurança.
#
# Serve para tolerar:
# - execução interrompida;
# - atraso de publicação;
# - pregão recente ainda não disponível.
#
# Arquivos locais válidos dentro dessa janela são
# simplesmente reutilizados. Não são baixados novamente.

SAFETY_LOOKBACK_DAYS = 7


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
# HASH
# ============================================================


def sha256_bytes(
    data: bytes,
) -> str:

    h = hashlib.sha256()

    h.update(
        data
    )

    return h.hexdigest()


def sha256_file(
    path: Path,
) -> str:

    h = hashlib.sha256()

    with path.open(
        "rb"
    ) as f:

        for chunk in iter(
            lambda: f.read(
                1024 * 1024
            ),
            b"",
        ):

            h.update(
                chunk
            )

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

    tmp.write_bytes(
        data
    )

    tmp.replace(
        path
    )


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
# EXTRAÇÃO DA DATA PELO NOME
# ============================================================


def extract_date_from_filename(
    filename: str,
) -> date | None:

    name = (
        str(filename)
        .strip()
        .upper()
    )

    if not name.startswith(
        "SPRE"
    ):

        return None

    digits = name[
        4:10
    ]

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

    bio = BytesIO(
        data
    )

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

        # Não carrega o ZIP inteiro na memória
        # apenas para verificar se ele é válido.

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
# DOWNLOAD DE UM PREGÃO
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

    # ========================================================
    # REUTILIZAÇÃO LOCAL
    # ========================================================

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

    # ========================================================
    # REMOVE ARQUIVO INVÁLIDO
    # ========================================================

    if local_path.exists():

        local_path.unlink()

    params = {
        "filelist":
            filename
    }

    # ========================================================
    # CONSULTA B3
    # ========================================================

    try:

        response = session.get(
            B3_DOWNLOAD_URL,
            params=params,
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

    # B3 pode responder sem arquivo válido em:
    #
    # - feriado;
    # - fim de semana;
    # - pregão ainda não publicado;
    # - data sem negociação.

    if not valid:

        return {
            "date":
                trading_date.isoformat(),

            "filename":
                filename,

            "status":
                "NOT_AVAILABLE",

            "size_bytes":
                len(
                    data
                ),
        }

    # ========================================================
    # SALVA SOMENTE APÓS VALIDAÇÃO
    # ========================================================

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
            len(
                data
            ),

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

        seen.add(
            resolved
        )

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

        if trading_date.year != CURRENT_YEAR:

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

            dates.append(
                d
            )

    if not dates:

        return None

    return max(
        dates
    )


# ============================================================
# CALENDÁRIO INCREMENTAL
# ============================================================


def candidate_dates(
    latest_local: date | None,
) -> list[date]:

    """
    PRIMEIRA EXECUÇÃO DO ANO
    ------------------------
    Se nenhum SPRE válido do ano estiver disponível
    localmente, faz bootstrap desde 1º de janeiro.

    EXECUÇÕES SEGUINTES
    -------------------
    Se já existe SPRE válido, consulta somente uma pequena
    janela a partir do último pregão local.

    Isso permite recuperar publicação atrasada sem consultar
    novamente janeiro -> hoje em toda execução.

    Feriados não são codificados manualmente.
    A B3 decide se o arquivo existe.
    """

    if latest_local is None:

        start = date(
            CURRENT_YEAR,
            1,
            1,
        )

    else:

        start = (
            latest_local
            - timedelta(
                days=SAFETY_LOOKBACK_DAYS
            )
        )

        year_start = date(
            CURRENT_YEAR,
            1,
            1,
        )

        if start < year_start:

            start = year_start

    end = TODAY

    if start > end:

        return []

    result: list[date] = []

    current = start

    while current <= end:

        # Segunda = 0
        # Sexta = 4

        if current.weekday() < 5:

            result.append(
                current
            )

        current += timedelta(
            days=1
        )

    return result


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    *,
    status: str,
    results: list[dict],
    valid_files: list[dict],
    latest_available_date: str | None,
    latest_before_update: str | None,
    bootstrap: bool,
) -> None:

    downloaded = sum(
        x.get(
            "status"
        ) == "DOWNLOADED"
        for x in results
    )

    reused = sum(
        x.get(
            "status"
        ) == "LOCAL_VALID"
        for x in results
    )

    unavailable = sum(
        x.get(
            "status"
        ) == "NOT_AVAILABLE"
        for x in results
    )

    network_errors = sum(
        x.get(
            "status"
        ) == "NETWORK_ERROR"
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
            "LIVE_B3_CURRENT_YEAR_V2_INCREMENTAL",

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

        "latest_before_update":
            latest_before_update,

        "latest_available_date":
            latest_available_date,

        "incremental_update": {
            "enabled":
                True,

            "bootstrap":
                bootstrap,

            "safety_lookback_days":
                SAFETY_LOOKBACK_DAYS,

            "full_year_rescan_each_run":
                False,
        },

        "statistics": {
            "candidate_dates_checked":
                len(
                    results
                ),

            "downloaded":
                int(
                    downloaded
                ),

            "reused_local":
                int(
                    reused
                ),

            "not_available":
                int(
                    unavailable
                ),

            "network_errors":
                int(
                    network_errors
                ),

            "http_errors":
                int(
                    http_errors
                ),

            "valid_local_files":
                len(
                    valid_files
                ),
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

    MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = MANIFEST_PATH.with_suffix(
        ".json.tmp"
    )

    tmp.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        MANIFEST_PATH
    )


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    ensure_directories()

    print(
        "=" * 72
    )

    print(
        "B3 LIVE DATA — "
        "ANO CORRENTE V2.0 INCREMENTAL"
    )

    print(
        "=" * 72
    )

    print(
        "Fonte:",
        (
            "B3 BVBG.186.01 — "
            "Simplified Price Report - Equities"
        ),
    )

    print(
        "Ano:",
        CURRENT_YEAR,
    )

    print(
        "Padrão:",
        "SPRE{YYMMDD}.zip",
    )

    print(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    print(
        "Atualização:",
        "INCREMENTAL",
    )

    print(
        "=" * 72
    )

    # ========================================================
    # INVENTÁRIO ANTES DA ATUALIZAÇÃO
    # ========================================================

    print(
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

    bootstrap = (
        latest_before is None
    )

    print(
        "Arquivos SPRE locais válidos:",
        len(
            valid_before
        ),
    )

    print(
        "Último pregão local:",
        (
            latest_before.isoformat()
            if latest_before
            else "NENHUM"
        ),
    )

    print(
        "Modo:",
        (
            "BOOTSTRAP"
            if bootstrap
            else "INCREMENTAL"
        ),
    )

    # ========================================================
    # DATAS A CONSULTAR
    # ========================================================

    print(
        "\n[2/4] Determinando datas "
        "que precisam ser verificadas..."
    )

    dates = candidate_dates(
        latest_before
    )

    print(
        "Datas candidatas:",
        len(
            dates
        ),
    )

    if dates:

        print(
            "Período:",
            dates[0].isoformat(),
            "→",
            dates[-1].isoformat(),
        )

    else:

        print(
            "Nenhuma data pendente."
        )

    # ========================================================
    # SESSÃO B3
    # ========================================================

    print(
        "\n[3/4] Atualização oficial B3..."
    )

    results: list[dict] = []

    if dates:

        try:

            print(
                "Criando sessão oficial B3..."
            )

            session = (
                create_b3_session()
            )

            print(
                "✓ Sessão B3 criada"
            )

        except Exception as exc:

            raise B3CurrentYearError(
                "Não foi possível criar "
                "sessão com a B3."
            ) from exc

        total = len(
            dates
        )

        for index, trading_date in enumerate(
            dates,
            start=1,
        ):

            filename = b3_filename(
                trading_date
            )

            print(
                f"[{index}/{total}] "
                f"{trading_date.isoformat()} "
                f"— {filename}"
            )

            result = download_trading_day(
                session,
                trading_date,
            )

            results.append(
                result
            )

            status = result.get(
                "status",
                "UNKNOWN",
            )

            if status == "DOWNLOADED":

                mb = (
                    result.get(
                        "size_bytes",
                        0,
                    )
                    / 1024
                    / 1024
                )

                print(
                    f"   ✓ BAIXADO "
                    f"({mb:.2f} MB)"
                )

            elif status == "LOCAL_VALID":

                print(
                    "   ✓ LOCAL VÁLIDO"
                )

            elif status == "NOT_AVAILABLE":

                print(
                    "   - SEM PREGÃO/"
                    "INDISPONÍVEL"
                )

            elif status == "NETWORK_ERROR":

                print(
                    "   ! ERRO DE REDE"
                )

            else:

                print(
                    f"   ! {status}"
                )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    # ========================================================
    # INVENTÁRIO FINAL
    # ========================================================

    print(
        "\n[4/4] Auditoria final..."
    )

    valid_files = (
        inventory_local_files()
    )

    latest = latest_local_date(
        valid_files
    )

    if latest is None:

        status = (
            "DATA_INSUFFICIENT"
        )

    else:

        status = (
            "CURRENT_YEAR_READY"
        )

    latest_iso = (
        latest.isoformat()
        if latest is not None
        else None
    )

    latest_before_iso = (
        latest_before.isoformat()
        if latest_before is not None
        else None
    )

    write_manifest(
        status=status,
        results=results,
        valid_files=valid_files,
        latest_available_date=latest_iso,
        latest_before_update=latest_before_iso,
        bootstrap=bootstrap,
    )

    # ========================================================
    # ESTATÍSTICAS
    # ========================================================

    downloaded = sum(
        x.get(
            "status"
        ) == "DOWNLOADED"
        for x in results
    )

    reused = sum(
        x.get(
            "status"
        ) == "LOCAL_VALID"
        for x in results
    )

    unavailable = sum(
        x.get(
            "status"
        ) == "NOT_AVAILABLE"
        for x in results
    )

    network_errors = sum(
        x.get(
            "status"
        ) == "NETWORK_ERROR"
        for x in results
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        "RESULTADO — B3 ANO CORRENTE"
    )

    print(
        "=" * 72
    )

    print(
        "Status:",
        status,
    )

    print(
        "Modo:",
        (
            "BOOTSTRAP"
            if bootstrap
            else "INCREMENTAL"
        ),
    )

    print(
        "Arquivos válidos:",
        len(
            valid_files
        ),
    )

    print(
        "Datas verificadas agora:",
        len(
            results
        ),
    )

    print(
        "Baixados agora:",
        downloaded,
    )

    print(
        "Reutilizados na janela:",
        reused,
    )

    print(
        "Sem pregão/indisponíveis:",
        unavailable,
    )

    print(
        "Erros de rede:",
        network_errors,
    )

    print(
        "Último pregão antes:",
        latest_before_iso,
    )

    print(
        "Último pregão disponível:",
        latest_iso,
    )

    print(
        "Manifest:",
        MANIFEST_PATH,
    )

    print()

    print(
        "Sector Engine alterado: NÃO"
    )

    print(
        "Quality Engine alterado: NÃO"
    )

    print(
        "Investability Engine alterado: NÃO"
    )

    print(
        "Valuation Engine alterado: NÃO"
    )

    print(
        "Technical Engine alterado: NÃO"
    )

    print(
        "=" * 72
    )

    if status != "CURRENT_YEAR_READY":

        print(
            "✗ DATA_INSUFFICIENT"
        )

        return 2

    if network_errors:

        print(
            "⚠ Camada disponível, mas ocorreram "
            "erros de rede durante a atualização."
        )

    print(
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

        print(
            "\nExecução interrompida."
        )

        sys.exit(
            130
        )

    except B3CurrentYearError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            str(
                exc
            ),
            file=sys.stderr,
        )

        sys.exit(
            2
        )

    except Exception as exc:

        print(
            "\nERRO:",
            repr(
                exc
            ),
            file=sys.stderr,
        )

        sys.exit(
            1
        )
