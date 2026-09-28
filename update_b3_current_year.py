from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# B3 INVESTMENT ENGINE
# CURRENT YEAR B3 DATA V1
#
# Fonte oficial:
# BVBG.186.01 - Simplified Price Report - Equities
#
# Esta camada NÃO altera:
# - Sector Engine
# - Quality Engine
# - Investability Engine
# - Valuation Engine
# - Technical Engine
#
# Objetivo:
# preparar a infraestrutura do ano corrente sem usar
# endpoint não comprovado ou fonte não oficial.
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

CURRENT_YEAR = datetime.now(
    timezone.utc
).year


class B3CurrentYearError(RuntimeError):
    pass


# ============================================================
# DIRETÓRIOS
# ============================================================


def ensure_directories() -> None:

    CURRENT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# CONFIGURAÇÃO
# ============================================================


def get_download_endpoint() -> str | None:

    """
    Endpoint oficial somente será utilizado depois de
    comprovado no ambiente de produção.

    Pode ser informado por variável de ambiente:

    B3_BVBG186_DOWNLOAD_URL

    Nenhum endereço é inventado pelo código.
    """

    value = os.getenv(
        "B3_BVBG186_DOWNLOAD_URL",
        "",
    ).strip()

    return value or None


# ============================================================
# INVENTÁRIO LOCAL
# ============================================================


def inventory_current_year() -> list[dict]:

    result = []

    if not CURRENT_DIR.exists():
        return result

    for path in sorted(
        CURRENT_DIR.rglob("*")
    ):

        if not path.is_file():
            continue

        result.append(
            {
                "file": str(
                    path.relative_to(ROOT)
                ),
                "size_bytes": int(
                    path.stat().st_size
                ),
                "modified_utc": (
                    datetime.fromtimestamp(
                        path.stat().st_mtime,
                        tz=timezone.utc,
                    ).isoformat()
                ),
            }
        )

    return result


# ============================================================
# MANIFEST
# ============================================================


def write_manifest(
    *,
    status: str,
    endpoint_configured: bool,
    files: list[dict],
    message: str,
) -> None:

    manifest = {
        "engine": "B3_INVESTMENT_ENGINE",
        "data_layer": (
            "LIVE_B3_CURRENT_YEAR_V1"
        ),
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "reference_year": CURRENT_YEAR,
        "source": {
            "institution": "B3",
            "dataset": (
                "BVBG.186.01 "
                "Simplified Price Report - Equities"
            ),
            "official": True,
        },
        "status": status,
        "endpoint_configured": (
            endpoint_configured
        ),
        "files": files,
        "message": message,
        "methodology": {
            "status": "FROZEN_UNCHANGED",
            "history_rule_years": 10,
            "minimum_daily_liquidity_brl": (
                6_000_000
            ),
            "sector_engine_altered": False,
            "quality_engine_altered": False,
            "investability_engine_altered": False,
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
        "B3 LIVE DATA — ANO CORRENTE"
    )
    print("=" * 72)

    print(
        "Ano:",
        CURRENT_YEAR,
    )

    print(
        "Fonte oficial:",
        (
            "BVBG.186.01 - "
            "Simplified Price Report - Equities"
        ),
    )

    print(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    print("=" * 72)

    endpoint = (
        get_download_endpoint()
    )

    files = (
        inventory_current_year()
    )

    # --------------------------------------------------------
    # Se já houver arquivos oficiais locais, registramos.
    # --------------------------------------------------------

    if files:

        print(
            "Arquivos do ano corrente "
            "já presentes:",
            len(files),
        )

        write_manifest(
            status="LOCAL_DATA_AVAILABLE",
            endpoint_configured=(
                endpoint is not None
            ),
            files=files,
            message=(
                "Existem arquivos locais do "
                "BVBG.186.01 para processamento."
            ),
        )

        print(
            "Status:",
            "LOCAL_DATA_AVAILABLE",
        )

        print(
            "Manifest:",
            MANIFEST_PATH,
        )

        return 0

    # --------------------------------------------------------
    # Não existe arquivo local e ainda não temos endpoint
    # oficial comprovado.
    #
    # Falha segura. NÃO usa Yahoo, scraping improvisado,
    # endpoint inventado ou dado aproximado.
    # --------------------------------------------------------

    if endpoint is None:

        message = (
            "Endpoint automático do BVBG.186.01 "
            "ainda não foi comprovado. "
            "Nenhum dado alternativo foi utilizado."
        )

        write_manifest(
            status="DATA_INSUFFICIENT",
            endpoint_configured=False,
            files=[],
            message=message,
        )

        print()
        print(
            "DATA_INSUFFICIENT"
        )

        print(
            message
        )

        print()
        print(
            "Investability executado: NÃO"
        )

        print(
            "Quality alterado: NÃO"
        )

        print(
            "Valuation alterado: NÃO"
        )

        print(
            "Technical alterado: NÃO"
        )

        print("=" * 72)

        return 2

    # --------------------------------------------------------
    # O endpoint foi configurado, mas esta V1 ainda não
    # realiza download até validarmos seu contrato real.
    # --------------------------------------------------------

    message = (
        "Endpoint configurado, mas o contrato "
        "de download ainda precisa ser validado "
        "antes da aquisição automática."
    )

    write_manifest(
        status="ENDPOINT_PENDING_VALIDATION",
        endpoint_configured=True,
        files=[],
        message=message,
    )

    print(
        "Status:",
        "ENDPOINT_PENDING_VALIDATION",
    )

    print(
        "Nenhum download realizado."
    )

    print(
        "Manifest:",
        MANIFEST_PATH,
    )

    return 2


if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        print(
            "\nExecução interrompida."
        )

        sys.exit(130)

    except Exception as exc:

        print(
            "\nERRO:",
            repr(exc),
            file=sys.stderr,
        )

        sys.exit(1)
