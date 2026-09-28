from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# B3 INVESTMENT ENGINE
# LIVE B3 HISTORICAL DATA UPDATER V1.2
#
# OBJETIVO
# ------------------------------------------------------------
# Manter localmente o COTAHIST oficial necessário para o
# Investability Engine V1.
#
# PRINCÍPIO:
# - arquivo histórico válido = NÃO baixar novamente
# - arquivo ausente = baixar uma única vez
# - download com progresso
# - sem HEAD duplicado
# - sem endpoints alternativos inválidos
# - metodologia de investimento NÃO é alterada
#
# IMPORTANTE
# ------------------------------------------------------------
# Esta camada é AQUISIÇÃO DE DADOS.
#
# Ela NÃO:
# - calcula Quality
# - calcula Investability
# - calcula Valuation
# - calcula ranking
# - altera qualquer motor validado
# ============================================================


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
B3_DIR = LIVE_DIR / "b3"
COTAHIST_DIR = B3_DIR / "cotahist"

MANIFEST_PATH = B3_DIR / "b3_manifest.json"


# ============================================================
# CONFIGURAÇÃO
# ============================================================

CURRENT_YEAR = datetime.now(timezone.utc).year

HISTORY_RULE_YEARS = 10

# Margem de segurança de 1 ano além da regra.
FIRST_REQUIRED_YEAR = (
    CURRENT_YEAR
    - HISTORY_RULE_YEARS
    - 1
)

LAST_CLOSED_YEAR = CURRENT_YEAR - 1


# Endpoint que acabamos de comprovar no Colab:
#
# HTTP 200
# Content-Type: application/x-zip-compressed
#
COTAHIST_URL = (
    "https://bvmf.bmfbovespa.com.br/"
    "InstDados/SerHist/"
    "COTAHIST_A{year}.ZIP"
)


CONNECT_TIMEOUT_SECONDS = 10

READ_TIMEOUT_SECONDS = 120

CHUNK_SIZE = 1024 * 1024


USER_AGENT = (
    "Mozilla/5.0 "
    "(X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


class B3DataError(RuntimeError):
    pass


# ============================================================
# DIRETÓRIOS
# ============================================================


def ensure_directories() -> None:

    COTAHIST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# HASH
# ============================================================


def sha256_file(path: Path) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:

        while True:

            chunk = f.read(
                CHUNK_SIZE
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


# ============================================================
# REQUEST
# ============================================================


def build_request(url: str):

    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/x-zip-compressed,"
                "application/zip,"
                "application/octet-stream,"
                "*/*"
            ),
            "Connection": "close",
        },
    )


# ============================================================
# VALIDAÇÃO COTAHIST
# ============================================================


def validate_cotahist_zip(
    path: Path,
    year: int,
) -> dict:

    if not path.exists():

        raise B3DataError(
            f"Arquivo inexistente: {path}"
        )

    if path.stat().st_size <= 0:

        raise B3DataError(
            f"Arquivo vazio: {path}"
        )

    if not zipfile.is_zipfile(path):

        raise B3DataError(
            f"ZIP inválido: {path}"
        )

    with zipfile.ZipFile(
        path,
        "r",
    ) as zf:

        txt_members = [
            name
            for name in zf.namelist()
            if (
                not name.endswith("/")
                and name.upper().endswith(
                    ".TXT"
                )
            )
        ]

        if not txt_members:

            raise B3DataError(
                f"ZIP sem TXT: {path.name}"
            )

        member = txt_members[0]

        info = zf.getinfo(member)

        if info.file_size <= 0:

            raise B3DataError(
                f"TXT vazio: {path.name}"
            )

        with zf.open(
            member,
            "r",
        ) as f:

            first_line = (
                f.readline()
            )

        if not first_line:

            raise B3DataError(
                f"COTAHIST vazio: {path.name}"
            )

        first_text = (
            first_line
            .decode(
                "latin-1",
                errors="replace",
            )
            .rstrip("\r\n")
        )

        if not first_text.startswith(
            "00"
        ):

            raise B3DataError(
                "Header COTAHIST inválido: "
                f"{path.name}"
            )

    return {
        "year": int(year),
        "zip": path.name,
        "zip_size": int(
            path.stat().st_size
        ),
        "txt_member": member,
        "txt_size": int(
            info.file_size
        ),
        "sha256": sha256_file(
            path
        ),
    }


# ============================================================
# DOWNLOAD COM PROGRESSO
# ============================================================


def download_with_progress(
    year: int,
    destination: Path,
) -> dict:

    url = COTAHIST_URL.format(
        year=year
    )

    fd, tmp_name = tempfile.mkstemp(
        prefix=(
            destination.name
            + "."
        ),
        suffix=".part",
        dir=str(
            destination.parent
        ),
    )

    os.close(fd)

    tmp_path = Path(
        tmp_name
    )

    started = time.time()

    try:

        request = build_request(
            url
        )

        with urllib.request.urlopen(
            request,
            timeout=READ_TIMEOUT_SECONDS,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            if status != 200:

                raise B3DataError(
                    f"HTTP {status}"
                )

            total_header = (
                response.headers.get(
                    "Content-Length"
                )
            )

            total_bytes = (
                int(total_header)
                if (
                    total_header
                    and total_header.isdigit()
                )
                else None
            )

            downloaded = 0

            with tmp_path.open(
                "wb"
            ) as f:

                while True:

                    chunk = (
                        response.read(
                            CHUNK_SIZE
                        )
                    )

                    if not chunk:
                        break

                    f.write(chunk)

                    downloaded += len(
                        chunk
                    )

                    mb = (
                        downloaded
                        / 1024
                        / 1024
                    )

                    if total_bytes:

                        pct = (
                            downloaded
                            / total_bytes
                            * 100
                        )

                        total_mb = (
                            total_bytes
                            / 1024
                            / 1024
                        )

                        print(
                            "\r"
                            f"   {mb:,.1f}"
                            f"/{total_mb:,.1f} MB "
                            f"({pct:5.1f}%)",
                            end="",
                            flush=True,
                        )

                    else:

                        print(
                            "\r"
                            f"   {mb:,.1f} MB",
                            end="",
                            flush=True,
                        )

        print()

        if (
            not tmp_path.exists()
            or tmp_path.stat().st_size
            <= 0
        ):

            raise B3DataError(
                "Download vazio."
            )

        tmp_path.replace(
            destination
        )

        validation = (
            validate_cotahist_zip(
                destination,
                year,
            )
        )

        elapsed = (
            time.time()
            - started
        )

        return {
            **validation,
            "status": "DOWNLOADED",
            "source_url": url,
            "download_seconds": (
                round(
                    elapsed,
                    2,
                )
            ),
        }

    except Exception:

        if tmp_path.exists():

            try:
                tmp_path.unlink()
            except Exception:
                pass

        raise


# ============================================================
# ATUALIZAÇÃO DE UM ANO
# ============================================================


def update_year(
    year: int,
) -> dict:

    destination = (
        COTAHIST_DIR
        / f"COTAHIST_A{year}.ZIP"
    )

    # --------------------------------------------------------
    # REGRA PRINCIPAL:
    #
    # Histórico já válido NÃO é baixado novamente.
    # --------------------------------------------------------

    if destination.exists():

        try:

            validation = (
                validate_cotahist_zip(
                    destination,
                    year,
                )
            )

            return {
                **validation,
                "status": (
                    "EXISTING_VALID"
                ),
                "source_url": None,
            }

        except Exception as exc:

            print(
                "\n   Arquivo local "
                "inválido. Será substituído:"
            )

            print(
                "  ",
                exc,
            )

            try:
                destination.unlink()
            except Exception:
                pass

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    try:

        return (
            download_with_progress(
                year=year,
                destination=destination,
            )
        )

    except urllib.error.HTTPError as exc:

        return {
            "year": year,
            "status": (
                "NOT_AVAILABLE"
            ),
            "source_url": (
                COTAHIST_URL.format(
                    year=year
                )
            ),
            "error": (
                f"HTTP {exc.code}"
            ),
        }

    except urllib.error.URLError as exc:

        return {
            "year": year,
            "status": (
                "DOWNLOAD_ERROR"
            ),
            "source_url": (
                COTAHIST_URL.format(
                    year=year
                )
            ),
            "error": str(
                exc.reason
            ),
        }

    except TimeoutError:

        return {
            "year": year,
            "status": (
                "DOWNLOAD_TIMEOUT"
            ),
            "source_url": (
                COTAHIST_URL.format(
                    year=year
                )
            ),
            "error": "TIMEOUT",
        }

    except Exception as exc:

        return {
            "year": year,
            "status": (
                "DOWNLOAD_ERROR"
            ),
            "source_url": (
                COTAHIST_URL.format(
                    year=year
                )
            ),
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


# ============================================================
# INVENTÁRIO
# ============================================================


def local_inventory() -> list[dict]:

    result = []

    for path in sorted(
        COTAHIST_DIR.glob(
            "COTAHIST_A*.ZIP"
        )
    ):

        try:

            year = int(
                path.stem.replace(
                    "COTAHIST_A",
                    "",
                )
            )

        except Exception:
            continue

        try:

            validation = (
                validate_cotahist_zip(
                    path,
                    year,
                )
            )

            result.append(
                {
                    **validation,
                    "valid": True,
                }
            )

        except Exception as exc:

            result.append(
                {
                    "year": year,
                    "zip": path.name,
                    "valid": False,
                    "error": str(exc),
                }
            )

    return result


# ============================================================
# FRESHNESS
# ============================================================


def build_freshness(
    inventory: list[dict],
) -> dict:

    valid_years = sorted(
        {
            int(item["year"])
            for item in inventory
            if item.get(
                "valid"
            )
        }
    )

    required_closed_years = list(
        range(
            FIRST_REQUIRED_YEAR,
            LAST_CLOSED_YEAR + 1,
        )
    )

    missing_closed_years = [
        year
        for year
        in required_closed_years
        if year not in valid_years
    ]

    historical_ready = (
        len(
            missing_closed_years
        )
        == 0
    )

    return {
        "current_year": (
            CURRENT_YEAR
        ),
        "first_required_year": (
            FIRST_REQUIRED_YEAR
        ),
        "last_closed_year": (
            LAST_CLOSED_YEAR
        ),
        "valid_years": (
            valid_years
        ),
        "missing_closed_years": (
            missing_closed_years
        ),
        "historical_ready": (
            historical_ready
        ),
        "current_year_daily_layer_required": (
            True
        ),
        "status": (
            "HISTORICAL_READY"
            if historical_ready
            else "DATA_INSUFFICIENT"
        ),
    }


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    updates: list[dict],
    inventory: list[dict],
    freshness: dict,
) -> None:

    manifest = {
        "engine": (
            "B3_INVESTMENT_ENGINE"
        ),
        "data_layer": (
            "LIVE_B3_COTAHIST_V1_2"
        ),
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "source": {
            "institution": "B3",
            "dataset": (
                "COTAHIST"
            ),
            "endpoint": (
                COTAHIST_URL
            ),
        },
        "required_history": {
            "rule_years": (
                HISTORY_RULE_YEARS
            ),
            "first_required_year": (
                FIRST_REQUIRED_YEAR
            ),
            "last_closed_year": (
                LAST_CLOSED_YEAR
            ),
        },
        "updates": updates,
        "inventory": inventory,
        "freshness": freshness,
        "methodology": {
            "status": (
                "FROZEN_UNCHANGED"
            ),
            "history_rule_years": 10,
            "minimum_daily_liquidity_brl": (
                6_000_000
            ),
            "identity": "CD_CVM",
            "sector_engine_altered": (
                False
            ),
            "quality_engine_altered": (
                False
            ),
            "investability_engine_altered": (
                False
            ),
            "valuation_engine_altered": (
                False
            ),
            "technical_engine_altered": (
                False
            ),
        },
    }

    MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = (
        MANIFEST_PATH.with_suffix(
            ".json.tmp"
        )
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

    print("=" * 72)
    print(
        "B3 LIVE DATA — COTAHIST V1.2"
    )
    print("=" * 72)

    print(
        "Fonte:",
        "B3 COTAHIST oficial",
    )

    print(
        "Histórico necessário:",
        (
            f"{FIRST_REQUIRED_YEAR}"
            f"–{LAST_CLOSED_YEAR}"
        ),
    )

    print(
        "Regra:",
        "10 anos",
    )

    print(
        "Liquidez mínima:",
        "R$ 6.000.000/dia",
    )

    print(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    print("=" * 72)

    updates = []

    years = list(
        range(
            FIRST_REQUIRED_YEAR,
            LAST_CLOSED_YEAR + 1,
        )
    )

    for index, year in enumerate(
        years,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(years)}] "
            f"COTAHIST {year}"
        )

        destination = (
            COTAHIST_DIR
            / f"COTAHIST_A{year}.ZIP"
        )

        if destination.exists():

            print(
                "   Verificando arquivo local..."
            )

        else:

            print(
                "   Arquivo ausente."
            )

            print(
                "   Baixando da B3..."
            )

        result = update_year(
            year
        )

        updates.append(
            result
        )

        status = result[
            "status"
        ]

        if status == (
            "EXISTING_VALID"
        ):

            size_mb = (
                result[
                    "zip_size"
                ]
                / 1024
                / 1024
            )

            print(
                "   ✓ LOCAL VÁLIDO "
                f"({size_mb:,.1f} MB)"
            )

        elif status == (
            "DOWNLOADED"
        ):

            size_mb = (
                result[
                    "zip_size"
                ]
                / 1024
                / 1024
            )

            print(
                "   ✓ DOWNLOAD CONCLUÍDO "
                f"({size_mb:,.1f} MB)"
            )

        else:

            print(
                "   ✗",
                status,
            )

            print(
                "    ",
                result.get(
                    "error",
                    "",
                ),
            )

    # --------------------------------------------------------
    # INVENTÁRIO FINAL
    # --------------------------------------------------------

    inventory = (
        local_inventory()
    )

    freshness = (
        build_freshness(
            inventory
        )
    )

    write_manifest(
        updates=updates,
        inventory=inventory,
        freshness=freshness,
    )

    print()
    print("=" * 72)
    print(
        "RESULTADO — B3 HISTÓRICO"
    )
    print("=" * 72)

    print(
        "Status:",
        freshness[
            "status"
        ],
    )

    print(
        "Anos válidos:",
        freshness[
            "valid_years"
        ],
    )

    print(
        "Anos ausentes:",
        freshness[
            "missing_closed_years"
        ],
    )

    print(
        "Histórico pronto:",
        (
            "SIM"
            if freshness[
                "historical_ready"
            ]
            else "NÃO"
        ),
    )

    print(
        "Manifest:",
        MANIFEST_PATH,
    )

    print()
    print(
        "Ano corrente:",
        CURRENT_YEAR,
    )

    print(
        "Camada diária do ano "
        "corrente necessária:",
        "SIM",
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

    print("=" * 72)

    if not freshness[
        "historical_ready"
    ]:

        print(
            "DATA_INSUFFICIENT:"
        )

        print(
            "Ainda faltam arquivos "
            "históricos obrigatórios."
        )

        return 2

    print(
        "✓ CAMADA HISTÓRICA B3 PRONTA"
    )

    print(
        "Próxima etapa:"
    )

    print(
        "dados B3 do ano corrente "
        "→ Investability V1"
    )

    return 0


if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "Execução interrompida."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print(
            "ERRO:",
            repr(exc),
            file=sys.stderr,
        )

        sys.exit(1)
