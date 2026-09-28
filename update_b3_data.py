from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# B3 INVESTMENT ENGINE
# LIVE B3 HISTORICAL DATA UPDATER V1.1
#
# Responsabilidade:
# - baixar COTAHIST oficial B3
# - manter histórico necessário à regra de 10 anos
# - validar ZIP/TXT
# - evitar esperas longas em endpoints indisponíveis
# - gerar manifesto de dados
#
# NÃO ALTERA:
# - Sector Engine
# - Quality Engine
# - Investability Engine
# - Valuation Engine
# - Technical Engine
# - metodologia congelada
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

# Precisamos de pelo menos 10 anos de histórico.
# Mantemos margem adicional de 1 ano.
FIRST_HISTORY_YEAR = CURRENT_YEAR - 11

DOWNLOAD_TIMEOUT = 12


# Endpoint histórico tradicional utilizado pela B3 para
# distribuição do COTAHIST.
COTAHIST_URL_TEMPLATES = [
    (
        "https://bvmf.bmfbovespa.com.br/"
        "InstDados/SerHist/"
        "COTAHIST_A{year}.ZIP"
    ),
]


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

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


# ============================================================
# HTTP
# ============================================================


def build_request(url: str):

    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/zip,"
                "application/octet-stream,"
                "*/*"
            ),
            "Connection": "close",
        },
    )


# ============================================================
# DOWNLOAD ATÔMICO
# ============================================================


def atomic_download(
    url: str,
    destination: Path,
    timeout: int = DOWNLOAD_TIMEOUT,
) -> None:

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, tmp_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=str(destination.parent),
    )

    os.close(fd)

    tmp_path = Path(tmp_name)

    try:

        request = build_request(url)

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            if not 200 <= status < 300:
                raise B3DataError(
                    f"HTTP {status}"
                )

            with tmp_path.open("wb") as f:

                shutil.copyfileobj(
                    response,
                    f,
                    length=1024 * 1024,
                )

        if (
            not tmp_path.exists()
            or tmp_path.stat().st_size == 0
        ):
            raise B3DataError(
                "download vazio"
            )

        tmp_path.replace(destination)

    except Exception:

        if tmp_path.exists():
            tmp_path.unlink()

        raise


# ============================================================
# VALIDAÇÃO COTAHIST
# ============================================================


def validate_cotahist_zip(
    path: Path,
    year: int,
) -> dict:

    if not path.exists():
        raise B3DataError(
            f"arquivo inexistente: {path}"
        )

    if path.stat().st_size == 0:
        raise B3DataError(
            f"arquivo vazio: {path}"
        )

    if not zipfile.is_zipfile(path):
        raise B3DataError(
            f"não é ZIP válido: {path}"
        )

    with zipfile.ZipFile(path, "r") as zf:

        txt_members = [
            name
            for name in zf.namelist()
            if (
                not name.endswith("/")
                and name.upper().endswith(".TXT")
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

        with zf.open(member, "r") as f:
            first_line = f.readline()

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

        if not first_text.startswith("00"):
            raise B3DataError(
                "header COTAHIST inválido: "
                f"{path.name}"
            )

    return {
        "year": year,
        "zip": path.name,
        "txt_member": member,
        "zip_size": int(
            path.stat().st_size
        ),
        "txt_size": int(
            info.file_size
        ),
        "sha256": sha256_file(path),
    }


# ============================================================
# URL
# ============================================================


def candidate_urls(
    year: int,
) -> list[str]:

    return [
        template.format(year=year)
        for template
        in COTAHIST_URL_TEMPLATES
    ]


# ============================================================
# ANO INDIVIDUAL
# ============================================================


def update_cotahist_year(
    year: int,
) -> dict:

    filename = (
        f"COTAHIST_A{year}.ZIP"
    )

    destination = (
        COTAHIST_DIR / filename
    )

    # -----------------------------------------------
    # Arquivo local já válido: não baixa novamente.
    # -----------------------------------------------

    if destination.exists():

        try:

            validation = validate_cotahist_zip(
                destination,
                year,
            )

            return {
                **validation,
                "status": "EXISTING_VALID",
                "source_url": None,
            }

        except Exception:

            try:
                destination.unlink()
            except Exception:
                pass

    # -----------------------------------------------
    # Download direto.
    #
    # NÃO fazemos HEAD antes do GET.
    # Isso elimina a espera duplicada da versão 1.0.
    # -----------------------------------------------

    errors = []

    for url in candidate_urls(year):

        try:

            atomic_download(
                url=url,
                destination=destination,
            )

            validation = validate_cotahist_zip(
                destination,
                year,
            )

            return {
                **validation,
                "status": "DOWNLOADED",
                "source_url": url,
            }

        except urllib.error.HTTPError as exc:

            errors.append(
                f"HTTP {exc.code}"
            )

        except urllib.error.URLError as exc:

            errors.append(
                f"URL_ERROR: {exc.reason}"
            )

        except TimeoutError:

            errors.append(
                "TIMEOUT"
            )

        except Exception as exc:

            errors.append(
                f"{type(exc).__name__}: {exc}"
            )

        if destination.exists():

            try:
                destination.unlink()
            except Exception:
                pass

    return {
        "year": year,
        "status": "NOT_AVAILABLE",
        "source_url": None,
        "errors": errors,
    }


# ============================================================
# INVENTÁRIO
# ============================================================


def local_inventory() -> list[dict]:

    inventory = []

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

            validation = validate_cotahist_zip(
                path,
                year,
            )

            inventory.append(
                {
                    **validation,
                    "valid": True,
                }
            )

        except Exception as exc:

            inventory.append(
                {
                    "year": year,
                    "zip": path.name,
                    "valid": False,
                    "error": str(exc),
                }
            )

    return inventory


# ============================================================
# FRESHNESS
# ============================================================


def validate_freshness(
    inventory: list[dict],
) -> dict:

    valid_years = sorted(
        {
            int(item["year"])
            for item in inventory
            if item.get("valid")
        }
    )

    if not valid_years:

        return {
            "status": "DATA_INSUFFICIENT",
            "earliest_year": None,
            "latest_year": None,
            "years_available": [],
            "current_year": CURRENT_YEAR,
            "current_year_available": False,
        }

    earliest = min(valid_years)
    latest = max(valid_years)

    return {
        "status": "AVAILABLE",
        "earliest_year": earliest,
        "latest_year": latest,
        "years_available": valid_years,
        "number_of_years": len(
            valid_years
        ),
        "current_year": CURRENT_YEAR,
        "current_year_available": (
            CURRENT_YEAR in valid_years
        ),
    }


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    results: list[dict],
    inventory: list[dict],
    freshness: dict,
) -> None:

    manifest = {
        "engine": (
            "B3_INVESTMENT_ENGINE"
        ),
        "data_layer": (
            "LIVE_B3_HISTORICAL_DATA_V1_1"
        ),
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "source": {
            "institution": "B3",
            "dataset": (
                "COTAHIST - "
                "Cotações Históricas"
            ),
        },
        "requested": {
            "first_year": (
                FIRST_HISTORY_YEAR
            ),
            "last_year": (
                CURRENT_YEAR
            ),
        },
        "freshness": freshness,
        "updates": results,
        "inventory": inventory,
        "methodology": {
            "status": (
                "FROZEN_UNCHANGED"
            ),
            "history_rule_years": 10,
            "minimum_daily_liquidity_brl": (
                6_000_000
            ),
            "official_identity": "CD_CVM",
            "sector_engine_altered": False,
            "quality_engine_altered": False,
            "investability_engine_altered": (
                False
            ),
            "valuation_engine_altered": False,
            "technical_engine_altered": False,
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

    tmp.replace(MANIFEST_PATH)


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    ensure_directories()

    print("=" * 72)
    print("ATUALIZANDO COTAHIST OFICIAL B3")
    print("=" * 72)

    print(
        "Período necessário:",
        f"{FIRST_HISTORY_YEAR}–{CURRENT_YEAR}",
    )

    print(
        "Regra de histórico:",
        "10 anos",
    )

    print(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    print("=" * 72)

    results = []

    for year in range(
        FIRST_HISTORY_YEAR,
        CURRENT_YEAR + 1,
    ):

        print(
            f"COTAHIST {year}...",
            end=" ",
            flush=True,
        )

        result = update_cotahist_year(
            year
        )

        results.append(result)

        status = result["status"]

        if status == "DOWNLOADED":

            size_mb = (
                result["zip_size"]
                / 1024
                / 1024
            )

            print(
                f"✓ baixado "
                f"({size_mb:.1f} MB)"
            )

        elif status == "EXISTING_VALID":

            print(
                "✓ local válido"
            )

        else:

            error_text = "; ".join(
                result.get(
                    "errors",
                    [],
                )
            )

            print(
                "− indisponível",
                error_text,
            )

    inventory = local_inventory()

    freshness = validate_freshness(
        inventory
    )

    write_manifest(
        results=results,
        inventory=inventory,
        freshness=freshness,
    )

    print()
    print("=" * 72)
    print("RESULTADO")
    print("=" * 72)

    print(
        "Status:",
        freshness["status"],
    )

    print(
        "Primeiro ano disponível:",
        freshness[
            "earliest_year"
        ],
    )

    print(
        "Último ano disponível:",
        freshness[
            "latest_year"
        ],
    )

    print(
        "Ano corrente disponível:",
        (
            "SIM"
            if freshness[
                "current_year_available"
            ]
            else "NÃO"
        ),
    )

    print(
        "Arquivos válidos:",
        sum(
            1
            for item in inventory
            if item.get("valid")
        ),
    )

    print(
        "Manifest:",
        MANIFEST_PATH,
    )

    print()
    print(
        "Investability Engine alterado: NÃO"
    )
    print(
        "Quality Engine alterado: NÃO"
    )
    print(
        "Valuation Engine alterado: NÃO"
    )
    print(
        "Technical Engine alterado: NÃO"
    )

    print("=" * 72)

    if not freshness[
        "current_year_available"
    ]:

        print(
            "AVISO:"
        )

        print(
            "O COTAHIST anual do ano corrente "
            "não está disponível nesta fonte."
        )

        print(
            "A próxima camada deverá completar "
            "2026 com dados oficiais do período "
            "corrente antes da investabilidade."
        )

    print()
    print(
        "✓ ATUALIZAÇÃO HISTÓRICA B3 CONCLUÍDA"
    )

    return 0


if __name__ == "__main__":

    try:

        sys.exit(main())

    except KeyboardInterrupt:

        print(
            "\nExecução interrompida pelo usuário."
        )

        sys.exit(130)

    except B3DataError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            exc,
            file=sys.stderr,
        )

        sys.exit(2)

    except Exception as exc:

        print(
            "\nERRO:",
            repr(exc),
            file=sys.stderr,
        )

        sys.exit(1)
