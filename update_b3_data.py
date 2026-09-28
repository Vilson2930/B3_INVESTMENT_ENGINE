from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# B3 INVESTMENT ENGINE
# LIVE B3 DATA UPDATER V1
#
# Responsabilidade:
# - adquirir COTAHIST oficial da B3
# - preservar arquivos históricos
# - atualizar anos disponíveis
# - validar ZIP/TXT
# - gerar manifesto
#
# NÃO:
# - calcula Quality
# - calcula Valuation
# - calcula ranking
# - altera Investability Engine V1
# - altera metodologia congelada
# ============================================================


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
B3_DIR = LIVE_DIR / "b3"
COTAHIST_DIR = B3_DIR / "cotahist"

MANIFEST_PATH = B3_DIR / "b3_manifest.json"


# ------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------

FIRST_HISTORY_YEAR = 2000

CURRENT_YEAR = datetime.now(
    timezone.utc
).year


# O COTAHIST anual segue o padrão histórico oficial da B3.
#
# Mantemos mais de uma URL candidata porque a B3 já alterou
# a infraestrutura de distribuição ao longo do tempo.
#
# Nenhuma URL alternativa muda a metodologia. Ela muda apenas
# a localização física do mesmo arquivo oficial.
COTAHIST_URL_TEMPLATES = [
    (
        "https://bvmf.bmfbovespa.com.br/"
        "InstDados/SerHist/"
        "COTAHIST_A{year}.ZIP"
    ),
    (
        "https://www.b3.com.br/"
        "p_for_download/"
        "COTAHIST_A{year}.ZIP"
    ),
]


USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; B3InvestmentEngine/1.0)"
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


def build_request(
    url: str,
    method: str = "GET",
):

    return urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )


def remote_exists(
    url: str,
    timeout: int = 30,
) -> bool:

    # Primeiro tenta HEAD
    try:

        req = build_request(
            url,
            method="HEAD",
        )

        with urllib.request.urlopen(
            req,
            timeout=timeout,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            if 200 <= status < 400:
                return True

    except Exception:
        pass

    # Alguns servidores da B3 não respondem HEAD
    # corretamente. Fazemos então GET parcial/normal.
    try:

        req = build_request(
            url,
            method="GET",
        )

        with urllib.request.urlopen(
            req,
            timeout=timeout,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            return 200 <= status < 400

    except Exception:
        return False


# ============================================================
# DOWNLOAD ATÔMICO
# ============================================================


def atomic_download(
    url: str,
    destination: Path,
    timeout: int = 120,
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

        req = build_request(
            url,
            method="GET",
        )

        with urllib.request.urlopen(
            req,
            timeout=timeout,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            if not (
                200 <= status < 300
            ):
                raise B3DataError(
                    f"HTTP {status}: {url}"
                )

            with tmp_path.open(
                "wb"
            ) as f:

                shutil.copyfileobj(
                    response,
                    f,
                )

        if (
            not tmp_path.exists()
            or tmp_path.stat().st_size == 0
        ):
            raise B3DataError(
                f"Download vazio: {url}"
            )

        tmp_path.replace(
            destination
        )

    except Exception:

        if tmp_path.exists():
            tmp_path.unlink()

        raise


# ============================================================
# VALIDAÇÃO COTAHIST
# ============================================================


def expected_txt_name(
    year: int,
) -> str:

    return (
        f"COTAHIST_A{year}.TXT"
    )


def validate_cotahist_zip(
    path: Path,
    year: int,
) -> dict:

    if not path.exists():

        raise B3DataError(
            f"Arquivo inexistente: {path}"
        )

    if not zipfile.is_zipfile(
        path
    ):

        raise B3DataError(
            f"Arquivo não é ZIP válido: {path}"
        )

    with zipfile.ZipFile(
        path,
        "r",
    ) as zf:

        members = [
            name
            for name in zf.namelist()
            if not name.endswith("/")
        ]

        txt_members = [
            name
            for name in members
            if name.upper().endswith(
                ".TXT"
            )
        ]

        if not txt_members:

            raise B3DataError(
                f"ZIP sem TXT: {path}"
            )

        # O nome interno pode variar em maiúsculas/minúsculas.
        # Não eliminamos o arquivo somente pelo nome.
        member = txt_members[0]

        info = zf.getinfo(
            member
        )

        if info.file_size <= 0:

            raise B3DataError(
                f"TXT vazio em {path}"
            )

        # Validação estrutural mínima do COTAHIST.
        #
        # Registro COTAHIST possui largura fixa de 245 bytes.
        # O arquivo possui header 00, registros 01 e trailer 99.
        with zf.open(
            member,
            "r",
        ) as f:

            first_line = f.readline()

        if not first_line:

            raise B3DataError(
                f"COTAHIST vazio: {path}"
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
                "Header COTAHIST inválido "
                f"em {path.name}"
            )

    return {
        "zip": path.name,
        "txt_member": member,
        "txt_size": int(
            info.file_size
        ),
        "zip_size": int(
            path.stat().st_size
        ),
        "sha256": sha256_file(
            path
        ),
    }


# ============================================================
# URLs
# ============================================================


def candidate_urls(
    year: int,
) -> list[str]:

    return [
        template.format(
            year=year
        )
        for template
        in COTAHIST_URL_TEMPLATES
    ]


# ============================================================
# DOWNLOAD POR ANO
# ============================================================


def update_cotahist_year(
    year: int,
) -> dict:

    filename = (
        f"COTAHIST_A{year}.ZIP"
    )

    destination = (
        COTAHIST_DIR
        / filename
    )

    # Se já existe e é válido, preserva.
    if destination.exists():

        try:

            validation = (
                validate_cotahist_zip(
                    destination,
                    year,
                )
            )

            return {
                "year": year,
                "status": "EXISTING_VALID",
                "source_url": None,
                **validation,
            }

        except Exception:

            # Arquivo local corrompido:
            # remove e baixa novamente.
            destination.unlink()

    errors = []

    for url in candidate_urls(
        year
    ):

        try:

            if not remote_exists(
                url
            ):
                errors.append(
                    f"não disponível: {url}"
                )
                continue

            atomic_download(
                url,
                destination,
            )

            validation = (
                validate_cotahist_zip(
                    destination,
                    year,
                )
            )

            return {
                "year": year,
                "status": "DOWNLOADED",
                "source_url": url,
                **validation,
            }

        except Exception as exc:

            errors.append(
                f"{url}: {exc}"
            )

            if destination.exists():
                destination.unlink()

    return {
        "year": year,
        "status": "NOT_AVAILABLE",
        "source_url": None,
        "errors": errors,
    }


# ============================================================
# INVENTÁRIO LOCAL
# ============================================================


def local_inventory() -> list[dict]:

    inventory = []

    for path in sorted(
        COTAHIST_DIR.glob(
            "COTAHIST_A*.ZIP"
        )
    ):

        stem = path.stem

        try:

            year = int(
                stem.replace(
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

            inventory.append(
                {
                    "year": year,
                    "valid": True,
                    **validation,
                }
            )

        except Exception as exc:

            inventory.append(
                {
                    "year": year,
                    "valid": False,
                    "zip": path.name,
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

        raise B3DataError(
            "Nenhum COTAHIST válido disponível."
        )

    latest_year = max(
        valid_years
    )

    # Para histórico de 10 anos precisamos pelo menos
    # de cobertura suficiente para o motor.
    earliest_year = min(
        valid_years
    )

    historical_coverage = (
        latest_year
        - earliest_year
        + 1
    )

    return {
        "earliest_year": earliest_year,
        "latest_year": latest_year,
        "years_available": valid_years,
        "historical_coverage_years": (
            historical_coverage
        ),
        "current_year": CURRENT_YEAR,
        "current_year_available": (
            CURRENT_YEAR
            in valid_years
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
            "LIVE_B3_DATA_V1"
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
            "official_page": (
                "B3 / Market Data / "
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
            "investability_engine_altered": (
                False
            ),
            "quality_engine_altered": (
                False
            ),
            "valuation_engine_altered": (
                False
            ),
            "sector_engine_altered": (
                False
            ),
            "technical_engine_altered": (
                False
            ),
            "history_rule_years": 10,
            "minimum_daily_liquidity_brl": (
                6_000_000
            ),
            "official_identity": (
                "CD_CVM"
            ),
        },
    }

    MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = (
        MANIFEST_PATH
        .with_suffix(
            ".json.tmp"
        )
    )

    temp.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temp.replace(
        MANIFEST_PATH
    )


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    print(
        "=" * 72
    )
    print(
        "ATUALIZANDO DADOS OFICIAIS B3"
    )
    print(
        "=" * 72
    )

    print(
        "Fonte: B3 — COTAHIST"
    )

    print(
        "Período solicitado:",
        f"{FIRST_HISTORY_YEAR}–{CURRENT_YEAR}",
    )

    print(
        "Metodologia:",
        "FROZEN_UNCHANGED",
    )

    print(
        "=" * 72
    )

    ensure_directories()

    results = []

    for year in range(
        FIRST_HISTORY_YEAR,
        CURRENT_YEAR + 1,
    ):

        result = (
            update_cotahist_year(
                year
            )
        )

        results.append(
            result
        )

        status = result[
            "status"
        ]

        if status in {
            "DOWNLOADED",
            "EXISTING_VALID",
        }:

            print(
                f"✓ COTAHIST {year}: "
                f"{status}"
            )

        else:

            print(
                f"− COTAHIST {year}: "
                "não disponível"
            )

    inventory = (
        local_inventory()
    )

    freshness = (
        validate_freshness(
            inventory
        )
    )

    write_manifest(
        results=results,
        inventory=inventory,
        freshness=freshness,
    )

    print()
    print(
        "=" * 72
    )
    print(
        "RESULTADO B3"
    )
    print(
        "=" * 72
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

    print(
        "=" * 72
    )

    # O ano corrente pode ainda não existir como COTAHIST anual.
    # Isso NÃO é tratado aqui como alteração metodológica.
    #
    # A camada de produção decidirá se complementa o ano corrente
    # com o boletim diário oficial B3.
    if not freshness[
        "current_year_available"
    ]:

        print(
            "AVISO: COTAHIST anual do ano "
            "corrente ainda não disponível."
        )

        print(
            "Será necessário complementar "
            "o ano corrente com dados oficiais "
            "diários da B3."
        )

    print(
        "✓ CAMADA B3 HISTÓRICA CONCLUÍDA"
    )

    return 0


if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except B3DataError as exc:

        print(
            "\nDATA_INSUFFICIENT:",
            exc,
            file=sys.stderr,
        )

        sys.exit(2)

    except Exception as exc:

        print(
            "\nERRO INESPERADO:",
            repr(exc),
            file=sys.stderr,
        )

        sys.exit(1)
