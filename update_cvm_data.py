from __future__ import annotations

import hashlib
import json
import random
import socket
import sys
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# B3 INVESTMENT ENGINE
# CAMADA DE PRODUÇÃO — ATUALIZAÇÃO OFICIAL CVM V2
# ============================================================
#
# RESPONSABILIDADE:
# - atualizar a matéria-prima oficial da CVM;
# - preservar a metodologia congelada;
# - NÃO calcular Quality Score;
# - NÃO calcular Valuation;
# - NÃO calcular ranking;
# - NÃO alterar checkpoints do estudo.
#
# CORREÇÃO V2:
# - retry automático para falhas transitórias;
# - exponential backoff;
# - tratamento de timeout;
# - tratamento de HTTP transitório;
# - download atômico preservado;
# - arquivo válido anterior nunca é substituído
#   por download parcial;
# - nenhuma imputação ou dado inventado.
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
    "B3_INVESTMENT_ENGINE/2.0 "
    "(official CVM public-data updater)"
)

TIMEOUT_SECONDS = 120

# Número total de tentativas para falhas transitórias.
MAX_RETRIES = 5

# Backoff:
# tentativa 1 -> ~2 s
# tentativa 2 -> ~4 s
# tentativa 3 -> ~8 s
# tentativa 4 -> ~16 s
# tentativa 5 -> falha definitiva
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 30.0

# Pequeno jitter evita repetir conexão exatamente
# no mesmo instante.
BACKOFF_JITTER_SECONDS = 0.75

# HTTPs normalmente transitórios.
TRANSIENT_HTTP_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

# O estudo congelado original começa em 2019.
# Para produção, mantemos essa origem histórica e avançamos
# automaticamente até o ano corrente.
FIRST_STUDY_YEAR = 2019


# ============================================================
# EXCEÇÕES
# ============================================================

class CVMDataError(RuntimeError):
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


# ============================================================
# RETRY / BACKOFF
# ============================================================

def retry_delay(
    failed_attempt: int,
) -> float:
    """
    failed_attempt começa em 1.

    Exemplo:
    1 -> aproximadamente 2 s
    2 -> aproximadamente 4 s
    3 -> aproximadamente 8 s
    4 -> aproximadamente 16 s
    """

    delay = min(
        BACKOFF_BASE_SECONDS
        * (2 ** (failed_attempt - 1)),
        BACKOFF_MAX_SECONDS,
    )

    delay += random.uniform(
        0.0,
        BACKOFF_JITTER_SECONDS,
    )

    return delay


def wait_before_retry(
    attempt: int,
    url: str,
    reason: str,
) -> None:

    delay = retry_delay(
        attempt
    )

    print(
        f"  ! tentativa {attempt}/{MAX_RETRIES} "
        f"falhou: {reason}",
        flush=True,
    )

    print(
        f"  ↻ nova tentativa em "
        f"{delay:.1f}s",
        flush=True,
    )

    print(
        f"    {url}",
        flush=True,
    )

    time.sleep(delay)


def is_transient_http_error(
    code: int,
) -> bool:

    return (
        code in TRANSIENT_HTTP_CODES
    )


# ============================================================
# CONEXÃO COM RETRY
# ============================================================

def open_with_retry(
    url: str,
    method: str = "GET",
):
    """
    Abre recurso oficial da CVM com retry para falhas
    transitórias de rede.

    Retorna o response aberto.

    O chamador deve usar:

        with open_with_retry(...) as response:
            ...

    HTTP 404 não é tratado aqui como indisponibilidade
    silenciosa. remote_exists() possui a semântica específica
    para isso.
    """

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

            if not is_transient_http_error(
                exc.code
            ):
                raise

            if attempt >= MAX_RETRIES:
                break

            wait_before_retry(
                attempt,
                url,
                f"HTTP {exc.code}",
            )

        except (
            URLError,
            TimeoutError,
            socket.timeout,
            ConnectionError,
            OSError,
        ) as exc:

            last_error = exc

            if attempt >= MAX_RETRIES:
                break

            wait_before_retry(
                attempt,
                url,
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

    raise CVMDataError(
        "Falha de conexão com a CVM após "
        f"{MAX_RETRIES} tentativas: "
        f"{url}. "
        f"Último erro: {last_error}"
    ) from last_error


# ============================================================
# DISPONIBILIDADE REMOTA
# ============================================================

def remote_exists(
    url: str,
) -> bool:
    """
    Confirma se um recurso oficial está disponível.

    Primeiro tenta HEAD.

    - 404 = recurso não disponível;
    - 400/403/405 = servidor pode não aceitar HEAD,
      então utiliza GET;
    - falhas transitórias recebem retry automático;
    - outros erros HTTP são considerados erro real.
    """

    try:

        with open_with_retry(
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

    # --------------------------------------------------------
    # FALLBACK GET
    # --------------------------------------------------------

    try:

        with open_with_retry(
            url,
            method="GET",
        ) as response:

            # Lê somente um byte para confirmar
            # disponibilidade.
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
# DOWNLOAD ATÔMICO COM RETRY
# ============================================================

def download_atomic(
    url: str,
    destination: Path,
) -> dict:
    """
    Baixa o recurso oficial para arquivo temporário.

    O arquivo definitivo somente é substituído quando:
    - a resposta HTTP é válida;
    - o download termina;
    - o arquivo temporário existe;
    - o arquivo temporário não está vazio.

    Se todas as tentativas falharem:
    - .tmp é removido;
    - eventual arquivo definitivo anterior permanece intacto;
    - a execução falha claramente.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        destination.with_suffix(
            destination.suffix + ".tmp"
        )
    )

    if temp_path.exists():
        temp_path.unlink()

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        if temp_path.exists():
            temp_path.unlink()

        request = build_request(
            url,
            method="GET",
        )

        try:

            with urlopen(
                request,
                timeout=TIMEOUT_SECONDS,
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

            # ------------------------------------------------
            # VALIDAÇÃO ANTES DA TROCA
            # ------------------------------------------------

            if (
                not temp_path.exists()
                or
                temp_path.stat().st_size
                == 0
            ):
                raise CVMDataError(
                    "Arquivo vazio recebido "
                    f"da CVM: {url}"
                )

            # ------------------------------------------------
            # TROCA ATÔMICA
            # ------------------------------------------------

            temp_path.replace(
                destination
            )

            return {
                "url": url,
                "path": str(
                    destination
                ),
                "size_bytes":
                    destination.stat().st_size,
                "sha256":
                    sha256_file(
                        destination
                    ),
                "downloaded_at_utc":
                    utc_now_iso(),
            }

        except HTTPError as exc:

            last_error = exc

            if temp_path.exists():
                temp_path.unlink()

            if not is_transient_http_error(
                exc.code
            ):
                raise CVMDataError(
                    f"Erro HTTP ao baixar "
                    f"{url}: {exc.code}"
                ) from exc

            if attempt >= MAX_RETRIES:
                break

            wait_before_retry(
                attempt,
                url,
                f"HTTP {exc.code}",
            )

        except (
            URLError,
            TimeoutError,
            socket.timeout,
            ConnectionError,
            OSError,
        ) as exc:

            last_error = exc

            if temp_path.exists():
                temp_path.unlink()

            if attempt >= MAX_RETRIES:
                break

            wait_before_retry(
                attempt,
                url,
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

        except CVMDataError as exc:

            last_error = exc

            if temp_path.exists():
                temp_path.unlink()

            if attempt >= MAX_RETRIES:
                break

            wait_before_retry(
                attempt,
                url,
                str(exc),
            )

        except Exception:

            if temp_path.exists():
                temp_path.unlink()

            raise

    if temp_path.exists():
        temp_path.unlink()

    raise CVMDataError(
        "Falha ao baixar recurso oficial "
        "da CVM após "
        f"{MAX_RETRIES} tentativas: "
        f"{url}. "
        f"Último erro: {last_error}"
    ) from last_error


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

    result = download_atomic(
        CADASTRO_URL,
        destination,
    )

    print(
        "✓ cadastro CVM atualizado",
        flush=True,
    )

    return result


# ============================================================
# DFP / ITR / FCA
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


def update_year_file(
    document_type: str,
    year: int,
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

    if not remote_exists(
        url
    ):

        return {
            "document_type":
                document_type,
            "year":
                year,
            "available":
                False,
            "url":
                url,
        }

    print(
        f"Atualizando "
        f"{document_type} {year}...",
        flush=True,
    )

    result = download_atomic(
        url,
        destination,
    )

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
# MANIFESTO / AUDITORIA
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

    manifest = {
        "engine":
            "B3_INVESTMENT_ENGINE",

        "layer":
            "LIVE_CVM_DATA",

        "generated_at_utc":
            utc_now_iso(),

        "updater": {
            "version":
                "V2_RETRY_BACKOFF",

            "max_retries":
                MAX_RETRIES,

            "timeout_seconds":
                TIMEOUT_SECONDS,

            "download_atomic":
                True,
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

    # --------------------------------------------------------
    # ITR
    # --------------------------------------------------------
    #
    # Regra original preservada.
    #
    # O ITR deve acompanhar o exercício corrente quando o
    # arquivo do ano corrente já existir.
    #
    # --------------------------------------------------------

    if latest_itr < current_year:

        raise CVMDataError(
            "DATA_STALE: "
            f"último ITR disponível = "
            f"{latest_itr}; "
            f"ano corrente = "
            f"{current_year}."
        )

    # --------------------------------------------------------
    # DFP
    # --------------------------------------------------------
    #
    # Regra original preservada.
    #
    # --------------------------------------------------------

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
        "ATUALIZAÇÃO OFICIAL CVM V2",
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
        "Rede: "
        f"{MAX_RETRIES} tentativas "
        "com backoff automático",
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
