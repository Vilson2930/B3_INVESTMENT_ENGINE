from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
import zipfile

from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# B3 INVESTMENT ENGINE
# CAMADA DE PRODUÇÃO — ATUALIZAÇÃO OFICIAL CVM V3
# INCREMENTAL / CACHE-FIRST / FAIL-SAFE
# ============================================================
#
# OBJETIVO
# ------------------------------------------------------------
# Atualizar exclusivamente a matéria-prima oficial da CVM.
#
# NÃO altera:
# - Quality Engine;
# - Valuation;
# - Investability;
# - ranking;
# - Technical Engine;
# - metodologia congelada.
#
# ARQUITETURA V3
# ------------------------------------------------------------
# 1. Arquivos históricos válidos já existentes NÃO são
#    baixados novamente.
#
# 2. Anos encerrados são tratados como histórico persistente.
#
# 3. Ano corrente pode ser atualizado porque DFP/ITR/FCA
#    podem receber novas versões durante o exercício.
#
# 4. Cadastro CVM é atualizado quando a rede está disponível.
#
# 5. Se a rede CVM estiver indisponível:
#       - não espera horas;
#       - não destrói arquivos locais;
#       - não inventa dados;
#       - utiliza somente arquivo local válido quando permitido.
#
# 6. Para dados que precisam ser atuais, a impossibilidade
#    de confirmar frescor é registrada explicitamente.
#
# 7. Downloads continuam atômicos.
#
# ============================================================


PROJECT_ROOT = Path(__file__).resolve().parent

DATA_DIR = PROJECT_ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
CVM_DIR = LIVE_DIR / "cvm"

DFP_DIR = CVM_DIR / "dfp"
ITR_DIR = CVM_DIR / "itr"
FCA_DIR = CVM_DIR / "fca"

MANIFEST_PATH = CVM_DIR / "cvm_manifest.json"


# ============================================================
# FONTES OFICIAIS
# ============================================================

CVM_BASE = "https://dados.cvm.gov.br"

CADASTRO_URL = (
    f"{CVM_BASE}/dados/CIA_ABERTA/CAD/DADOS/"
    "cad_cia_aberta.csv"
)

DFP_BASE_URL = (
    f"{CVM_BASE}/dados/CIA_ABERTA/DOC/DFP/DADOS"
)

ITR_BASE_URL = (
    f"{CVM_BASE}/dados/CIA_ABERTA/DOC/ITR/DADOS"
)

FCA_BASE_URL = (
    f"{CVM_BASE}/dados/CIA_ABERTA/DOC/FCA/DADOS"
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

USER_AGENT = (
    "B3_INVESTMENT_ENGINE/3.0 "
    "(official CVM public-data updater)"
)

TIMEOUT_SECONDS = 20

# Não transformar indisponibilidade persistente em horas
# de espera.
MAX_RETRIES = 2

RETRY_DELAY_SECONDS = 3

FIRST_STUDY_YEAR = 2019

TRANSIENT_HTTP_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}


# ============================================================
# EXCEÇÕES
# ============================================================

class CVMDataError(RuntimeError):
    pass


class CVMNetworkError(CVMDataError):
    pass


# ============================================================
# UTILIDADES
# ============================================================

def utc_now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def ensure_directories() -> None:

    for directory in (
        DATA_DIR,
        LIVE_DIR,
        CVM_DIR,
        DFP_DIR,
        ITR_DIR,
        FCA_DIR,
    ):

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def sha256_file(
    path: Path,
) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as file:

        for chunk in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):

            digest.update(chunk)

    return digest.hexdigest()


def build_request(
    url: str,
    method: str = "GET",
) -> Request:

    return Request(
        url=url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Connection": "close",
        },
    )


def file_metadata(
    path: Path,
    source: str,
) -> dict:

    return {
        "url": source,
        "path": str(path),
        "size_bytes": (
            path.stat().st_size
        ),
        "sha256": sha256_file(
            path
        ),
    }


# ============================================================
# VALIDAÇÃO LOCAL
# ============================================================

def valid_nonempty_file(
    path: Path,
) -> bool:

    try:

        return (
            path.exists()
            and
            path.is_file()
            and
            path.stat().st_size > 0
        )

    except OSError:

        return False


def valid_csv_file(
    path: Path,
) -> bool:

    if not valid_nonempty_file(
        path
    ):
        return False

    try:

        with path.open(
            "rb"
        ) as file:

            sample = file.read(
                4096
            )

        if not sample:
            return False

        # Cadastro oficial da CVM é texto/CSV.
        # Não tentamos reinterpretar seu conteúdo.
        return True

    except OSError:

        return False


def valid_zip_file(
    path: Path,
) -> bool:

    if not valid_nonempty_file(
        path
    ):
        return False

    try:

        with zipfile.ZipFile(
            path,
            "r",
        ) as archive:

            if not archive.namelist():
                return False

            bad_file = archive.testzip()

            return bad_file is None

    except (
        zipfile.BadZipFile,
        OSError,
    ):

        return False


# ============================================================
# REDE
# ============================================================

def network_request(
    url: str,
    method: str = "GET",
):

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        request = build_request(
            url,
            method=method,
        )

        try:

            return urlopen(
                request,
                timeout=TIMEOUT_SECONDS,
            )

        except HTTPError as exc:

            last_error = exc

            # HTTP não transitório:
            # deixa o chamador decidir a semântica.
            if (
                exc.code
                not in TRANSIENT_HTTP_CODES
            ):

                raise

        except (
            URLError,
            TimeoutError,
            socket.timeout,
            ConnectionError,
            OSError,
        ) as exc:

            last_error = exc

        if attempt < MAX_RETRIES:

            print(
                f"  ! rede CVM indisponível "
                f"— tentativa "
                f"{attempt}/{MAX_RETRIES}",
                flush=True,
            )

            print(
                f"  ↻ nova tentativa em "
                f"{RETRY_DELAY_SECONDS}s",
                flush=True,
            )

            time.sleep(
                RETRY_DELAY_SECONDS
            )

    raise CVMNetworkError(
        "CVM inacessível após "
        f"{MAX_RETRIES} tentativas. "
        f"Último erro: {last_error}"
    ) from last_error


def remote_exists(
    url: str,
) -> bool:

    try:

        with network_request(
            url,
            method="HEAD",
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            return (
                200 <= status < 400
            )

    except HTTPError as exc:

        if exc.code == 404:
            return False

        if exc.code not in (
            400,
            403,
            405,
        ):

            raise CVMDataError(
                f"Erro HTTP ao consultar "
                f"{url}: {exc.code}"
            ) from exc

    # Alguns servidores recusam HEAD.
    try:

        with network_request(
            url,
            method="GET",
        ) as response:

            response.read(1)

            status = getattr(
                response,
                "status",
                200,
            )

            return (
                200 <= status < 400
            )

    except HTTPError as exc:

        if exc.code == 404:
            return False

        raise CVMDataError(
            f"Erro HTTP ao consultar "
            f"{url}: {exc.code}"
        ) from exc


# ============================================================
# DOWNLOAD ATÔMICO
# ============================================================

def download_atomic(
    url: str,
    destination: Path,
    validator,
) -> dict:

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    if temp_path.exists():
        temp_path.unlink()

    try:

        with network_request(
            url,
            method="GET",
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            if not (
                200 <= status < 300
            ):

                raise CVMDataError(
                    f"HTTP {status}: {url}"
                )

            with temp_path.open(
                "wb"
            ) as output:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(chunk)

        if not validator(
            temp_path
        ):

            raise CVMDataError(
                "Arquivo recebido da CVM "
                "é vazio, inválido ou corrompido: "
                f"{url}"
            )

        temp_path.replace(
            destination
        )

    except Exception:

        if temp_path.exists():
            temp_path.unlink()

        raise

    result = file_metadata(
        destination,
        url,
    )

    result.update(
        {
            "downloaded_at_utc":
                utc_now_iso(),

            "source_mode":
                "DOWNLOADED",
        }
    )

    return result


# ============================================================
# CADASTRO CVM
# ============================================================

def update_company_registry() -> dict:

    print(
        "\nAtualizando cadastro CVM...",
        flush=True,
    )

    destination = (
        CVM_DIR
        /
        "cad_cia_aberta.csv"
    )

    local_valid = valid_csv_file(
        destination
    )

    try:

        result = download_atomic(
            CADASTRO_URL,
            destination,
            valid_csv_file,
        )

        print(
            "✓ cadastro CVM atualizado",
            flush=True,
        )

        return result

    except CVMNetworkError as exc:

        if not local_valid:
            raise

        print(
            "  ! CVM temporariamente "
            "inacessível.",
            flush=True,
        )

        print(
            "  ✓ cadastro local válido "
            "preservado.",
            flush=True,
        )

        result = file_metadata(
            destination,
            CADASTRO_URL,
        )

        result.update(
            {
                "source_mode":
                    "LOCAL_FALLBACK_NETWORK_UNAVAILABLE",

                "network_error":
                    str(exc),

                "freshness_confirmed":
                    False,
            }
        )

        return result


# ============================================================
# URLs DFP / ITR / FCA
# ============================================================

def dfp_url(
    year: int,
) -> str:

    return (
        f"{DFP_BASE_URL}/"
        f"dfp_cia_aberta_{year}.zip"
    )


def itr_url(
    year: int,
) -> str:

    return (
        f"{ITR_BASE_URL}/"
        f"itr_cia_aberta_{year}.zip"
    )


def fca_url(
    year: int,
) -> str:

    return (
        f"{FCA_BASE_URL}/"
        f"fca_cia_aberta_{year}.zip"
    )


# ============================================================
# ARQUIVO ANUAL
# ============================================================

def update_year_file(
    document_type: str,
    year: int,
    current_year: int,
) -> dict:

    document_type = (
        document_type
        .strip()
        .upper()
    )

    if document_type == "DFP":

        url = dfp_url(
            year
        )

        destination = (
            DFP_DIR
            /
            f"dfp_cia_aberta_{year}.zip"
        )

    elif document_type == "ITR":

        url = itr_url(
            year
        )

        destination = (
            ITR_DIR
            /
            f"itr_cia_aberta_{year}.zip"
        )

    elif document_type == "FCA":

        url = fca_url(
            year
        )

        destination = (
            FCA_DIR
            /
            f"fca_cia_aberta_{year}.zip"
        )

    else:

        raise ValueError(
            f"Tipo inválido: "
            f"{document_type}"
        )

    local_valid = valid_zip_file(
        destination
    )

    historical_closed_year = (
        year < current_year
    )

    # ========================================================
    # ANOS ENCERRADOS
    # ========================================================
    #
    # Arquivo válido já armazenado:
    # não baixa novamente.
    #
    # ========================================================

    if (
        historical_closed_year
        and
        local_valid
    ):

        print(
            f"✓ {document_type} {year}: "
            "LOCAL_VALID",
            flush=True,
        )

        result = file_metadata(
            destination,
            url,
        )

        result.update(
            {
                "document_type":
                    document_type,

                "year":
                    year,

                "available":
                    True,

                "source_mode":
                    "LOCAL_VALID",

                "freshness_confirmed":
                    True,
            }
        )

        return result

    # ========================================================
    # ANO CORRENTE OU ARQUIVO HISTÓRICO AUSENTE
    # ========================================================

    try:

        exists = remote_exists(
            url
        )

    except CVMNetworkError as exc:

        if local_valid:

            print(
                f"  ! {document_type} {year}: "
                "CVM inacessível; "
                "arquivo local válido preservado.",
                flush=True,
            )

            result = file_metadata(
                destination,
                url,
            )

            result.update(
                {
                    "document_type":
                        document_type,

                    "year":
                        year,

                    "available":
                        True,

                    "source_mode":
                        "LOCAL_FALLBACK_NETWORK_UNAVAILABLE",

                    "freshness_confirmed":
                        False,

                    "network_error":
                        str(exc),
                }
            )

            return result

        raise

    if not exists:

        if local_valid:

            print(
                f"✓ {document_type} {year}: "
                "arquivo local válido; "
                "recurso remoto não disponível.",
                flush=True,
            )

            result = file_metadata(
                destination,
                url,
            )

            result.update(
                {
                    "document_type":
                        document_type,

                    "year":
                        year,

                    "available":
                        True,

                    "source_mode":
                        "LOCAL_VALID_REMOTE_NOT_AVAILABLE",

                    "freshness_confirmed":
                        False,
                }
            )

            return result

        return {
            "document_type":
                document_type,

            "year":
                year,

            "available":
                False,

            "url":
                url,

            "source_mode":
                "REMOTE_NOT_AVAILABLE",

            "freshness_confirmed":
                True,
        }

    print(
        f"Atualizando "
        f"{document_type} {year}...",
        flush=True,
    )

    try:

        result = download_atomic(
            url,
            destination,
            valid_zip_file,
        )

    except CVMNetworkError as exc:

        if not local_valid:
            raise

        print(
            f"  ! download "
            f"{document_type} {year} "
            "não concluído.",
            flush=True,
        )

        print(
            "  ✓ versão local válida "
            "preservada.",
            flush=True,
        )

        result = file_metadata(
            destination,
            url,
        )

        result.update(
            {
                "source_mode":
                    "LOCAL_FALLBACK_NETWORK_UNAVAILABLE",

                "freshness_confirmed":
                    False,

                "network_error":
                    str(exc),
            }
        )

    else:

        result[
            "freshness_confirmed"
        ] = True

    result.update(
        {
            "document_type":
                document_type,

            "year":
                year,

            "available":
                True,
        }
    )

    print(
        f"✓ {document_type} {year}",
        flush=True,
    )

    return result


# ============================================================
# MANIFESTO
# ============================================================

def write_manifest(
    registry: dict,
    dfp_results: list[dict],
    itr_results: list[dict],
    fca_results: list[dict],
) -> dict:

    available_dfp = [
        x["year"]
        for x in dfp_results
        if x.get(
            "available"
        )
    ]

    available_itr = [
        x["year"]
        for x in itr_results
        if x.get(
            "available"
        )
    ]

    available_fca = [
        x["year"]
        for x in fca_results
        if x.get(
            "available"
        )
    ]

    all_results = (
        [registry]
        + dfp_results
        + itr_results
        + fca_results
    )

    network_fallback_used = any(
        x.get("source_mode")
        ==
        "LOCAL_FALLBACK_NETWORK_UNAVAILABLE"
        for x in all_results
    )

    manifest = {
        "engine":
            "B3_INVESTMENT_ENGINE",

        "layer":
            "LIVE_CVM_DATA",

        "generated_at_utc":
            utc_now_iso(),

        "updater": {
            "version":
                "V3_INCREMENTAL_CACHE_FIRST",

            "timeout_seconds":
                TIMEOUT_SECONDS,

            "max_retries":
                MAX_RETRIES,

            "historical_cache":
                True,

            "atomic_download":
                True,

            "network_fallback_used":
                network_fallback_used,
        },

        "methodology": {
            "status":
                "FROZEN_UNCHANGED",

            "quality_engine_modified":
                False,

            "valuation_modified":
                False,

            "technical_engine_modified":
                False,
        },

        "source": {
            "provider":
                "CVM",

            "official_base":
                CVM_BASE,
        },

        "registry":
            registry,

        "dfp": {
            "first_requested_year":
                FIRST_STUDY_YEAR,

            "latest_available_year":
                (
                    max(
                        available_dfp
                    )
                    if available_dfp
                    else None
                ),

            "files":
                dfp_results,
        },

        "itr": {
            "first_requested_year":
                FIRST_STUDY_YEAR,

            "latest_available_year":
                (
                    max(
                        available_itr
                    )
                    if available_itr
                    else None
                ),

            "files":
                itr_results,
        },

        "fca": {
            "first_requested_year":
                FIRST_STUDY_YEAR,

            "latest_available_year":
                (
                    max(
                        available_fca
                    )
                    if available_fca
                    else None
                ),

            "files":
                fca_results,
        },
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return manifest


# ============================================================
# VALIDAÇÃO DE FRESCOR
# ============================================================

def validate_current_data(
    manifest: dict,
    current_year: int,
) -> None:

    latest_dfp = (
        manifest["dfp"]
        ["latest_available_year"]
    )

    latest_itr = (
        manifest["itr"]
        ["latest_available_year"]
    )

    if latest_dfp is None:

        raise CVMDataError(
            "DATA_INSUFFICIENT: "
            "nenhum DFP disponível."
        )

    if latest_itr is None:

        raise CVMDataError(
            "DATA_INSUFFICIENT: "
            "nenhum ITR disponível."
        )

    # Regra original preservada.
    if latest_itr < current_year:

        raise CVMDataError(
            "DATA_STALE: "
            f"último ITR disponível = "
            f"{latest_itr}; "
            f"ano corrente = "
            f"{current_year}."
        )

    # Regra original preservada.
    if latest_dfp < (
        current_year - 1
    ):

        raise CVMDataError(
            "DATA_STALE: "
            f"último DFP disponível = "
            f"{latest_dfp}; "
            f"ano corrente = "
            f"{current_year}."
        )


# ============================================================
# EXECUÇÃO
# ============================================================

def main() -> int:

    print(
        "=" * 80,
        flush=True,
    )

    print(
        "B3 INVESTMENT ENGINE",
        flush=True,
    )

    print(
        "ATUALIZAÇÃO OFICIAL CVM V3",
        flush=True,
    )

    print(
        "INCREMENTAL / CACHE-FIRST",
        flush=True,
    )

    print(
        "=" * 80,
        flush=True,
    )

    ensure_directories()

    current_year = datetime.now(
        timezone.utc
    ).year

    years = list(
        range(
            FIRST_STUDY_YEAR,
            current_year + 1,
        )
    )

    print(
        f"\nPeríodo solicitado: "
        f"{years[0]}–{years[-1]}",
        flush=True,
    )

    print(
        "Metodologia fundamental: "
        "CONGELADA / NÃO ALTERADA",
        flush=True,
    )

    print(
        "Arquitetura: "
        "histórico local válido não é "
        "baixado novamente",
        flush=True,
    )

    print(
        "Rede: "
        f"{MAX_RETRIES} tentativas; "
        f"timeout {TIMEOUT_SECONDS}s",
        flush=True,
    )

    # ========================================================
    # CADASTRO
    # ========================================================

    registry = (
        update_company_registry()
    )

    # ========================================================
    # DFP
    # ========================================================

    print(
        "\n" + "-" * 80,
        flush=True,
    )

    print(
        "DFP",
        flush=True,
    )

    print(
        "-" * 80,
        flush=True,
    )

    dfp_results = []

    for year in years:

        result = update_year_file(
            "DFP",
            year,
            current_year,
        )

        dfp_results.append(
            result
        )

        if not result[
            "available"
        ]:

            print(
                f"- DFP {year}: "
                "não disponível",
                flush=True,
            )

    # ========================================================
    # ITR
    # ========================================================

    print(
        "\n" + "-" * 80,
        flush=True,
    )

    print(
        "ITR",
        flush=True,
    )

    print(
        "-" * 80,
        flush=True,
    )

    itr_results = []

    for year in years:

        result = update_year_file(
            "ITR",
            year,
            current_year,
        )

        itr_results.append(
            result
        )

        if not result[
            "available"
        ]:

            print(
                f"- ITR {year}: "
                "não disponível",
                flush=True,
            )

    # ========================================================
    # FCA
    # ========================================================

    print(
        "\n" + "-" * 80,
        flush=True,
    )

    print(
        "FCA",
        flush=True,
    )

    print(
        "-" * 80,
        flush=True,
    )

    fca_results = []

    for year in years:

        result = update_year_file(
            "FCA",
            year,
            current_year,
        )

        fca_results.append(
            result
        )

        if not result[
            "available"
        ]:

            print(
                f"- FCA {year}: "
                "não disponível",
                flush=True,
            )

    # ========================================================
    # MANIFESTO
    # ========================================================

    manifest = write_manifest(
        registry,
        dfp_results,
        itr_results,
        fca_results,
    )

    # ========================================================
    # FRESHNESS
    # ========================================================

    validate_current_data(
        manifest,
        current_year,
    )

    # ========================================================
    # FINAL
    # ========================================================

    print(
        "\n" + "=" * 80,
        flush=True,
    )

    print(
        "ATUALIZAÇÃO CVM CONCLUÍDA",
        flush=True,
    )

    print(
        "=" * 80,
        flush=True,
    )

    print(
        "Último DFP disponível:",
        manifest["dfp"]
        ["latest_available_year"],
        flush=True,
    )

    print(
        "Último ITR disponível:",
        manifest["itr"]
        ["latest_available_year"],
        flush=True,
    )

    print(
        "Último FCA disponível:",
        manifest["fca"]
        ["latest_available_year"],
        flush=True,
    )

    print(
        "Fallback de rede utilizado:",
        manifest["updater"]
        ["network_fallback_used"],
        flush=True,
    )

    print(
        "Manifesto:",
        MANIFEST_PATH,
        flush=True,
    )

    print(
        "\nQuality Engine alterado: NÃO",
        flush=True,
    )

    print(
        "Valuation alterado: NÃO",
        flush=True,
    )

    print(
        "Technical Engine alterado: NÃO",
        flush=True,
    )

    print(
        "=" * 80,
        flush=True,
    )

    return 0


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except CVMNetworkError as exc:

        print(
            "\nERRO DE REDE CVM: "
            f"{exc}",
            file=sys.stderr,
            flush=True,
        )

        sys.exit(2)

    except CVMDataError as exc:

        print(
            f"\nERRO CVM: {exc}",
            file=sys.stderr,
            flush=True,
        )

        sys.exit(2)

    except Exception as exc:

        print(
            "\nERRO NÃO PREVISTO: "
            f"{type(exc).__name__}: "
            f"{exc}",
            file=sys.stderr,
            flush=True,
        )

        sys.exit(1)
