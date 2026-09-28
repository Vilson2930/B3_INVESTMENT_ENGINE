from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# B3 INVESTMENT ENGINE
# CAMADA DE PRODUÇÃO — ATUALIZAÇÃO OFICIAL CVM
#
# RESPONSABILIDADE:
# - atualizar a matéria-prima oficial da CVM;
# - preservar a metodologia congelada;
# - NÃO calcular Quality Score;
# - NÃO calcular Valuation;
# - NÃO calcular ranking;
# - NÃO alterar checkpoints do estudo.
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
    "B3_INVESTMENT_ENGINE/1.0 "
    "(official CVM public-data updater)"
)

TIMEOUT_SECONDS = 120

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
    return datetime.now(timezone.utc).isoformat()


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
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
        },
    )


def remote_exists(url: str) -> bool:
    """
    Confirma se um recurso oficial está disponível.

    Primeiro tenta HEAD.
    Se o servidor não aceitar HEAD, tenta GET sem
    carregar o arquivo inteiro.
    """

    try:

        request = build_request(
            url,
            method="HEAD",
        )

        with urlopen(
            request,
            timeout=TIMEOUT_SECONDS,
        ) as response:

            status = getattr(
                response,
                "status",
                200,
            )

            return 200 <= status < 400

    except HTTPError as exc:

        if exc.code == 404:
            return False

        # Alguns servidores podem recusar HEAD.
        if exc.code not in (
            400,
            403,
            405,
        ):
            raise CVMDataError(
                f"Erro HTTP ao consultar {url}: "
                f"{exc.code}"
            ) from exc

    except URLError as exc:
        raise CVMDataError(
            f"Falha de conexão com a CVM: {exc}"
        ) from exc

    # Fallback GET
    try:

        request = build_request(
            url,
            method="GET",
        )

        with urlopen(
            request,
            timeout=TIMEOUT_SECONDS,
        ) as response:

            response.read(1)

            status = getattr(
                response,
                "status",
                200,
            )

            return 200 <= status < 400

    except HTTPError as exc:

        if exc.code == 404:
            return False

        raise CVMDataError(
            f"Erro HTTP ao consultar {url}: "
            f"{exc.code}"
        ) from exc

    except URLError as exc:
        raise CVMDataError(
            f"Falha de conexão com a CVM: {exc}"
        ) from exc


def download_atomic(
    url: str,
    destination: Path,
) -> dict:
    """
    Baixa para arquivo temporário e somente depois
    substitui o arquivo definitivo.

    Evita deixar arquivo parcial/corrompido caso
    a execução seja interrompida.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    if temp_path.exists():
        temp_path.unlink()

    request = build_request(url)

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

            with temp_path.open("wb") as output:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(chunk)

    except Exception:

        if temp_path.exists():
            temp_path.unlink()

        raise

    if (
        not temp_path.exists()
        or temp_path.stat().st_size == 0
    ):
        raise CVMDataError(
            f"Arquivo vazio recebido da CVM: {url}"
        )

    temp_path.replace(destination)

    return {
        "url": url,
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "downloaded_at_utc": utc_now_iso(),
    }


# ============================================================
# CADASTRO CVM
# ============================================================

def update_company_registry() -> dict:

    print("\nAtualizando cadastro CVM...")

    destination = (
        CVM_DIR /
        "cad_cia_aberta.csv"
    )

    result = download_atomic(
        CADASTRO_URL,
        destination,
    )

    print(
        "✓ cadastro CVM atualizado"
    )

    return result


# ============================================================
# DFP / ITR
# ============================================================

def dfp_url(year: int) -> str:
    return (
        f"{DFP_BASE_URL}/"
        f"dfp_cia_aberta_{year}.zip"
    )


def itr_url(year: int) -> str:
    return (
        f"{ITR_BASE_URL}/"
        f"itr_cia_aberta_{year}.zip"
    )


def fca_url(year: int) -> str:
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

        url = dfp_url(year)

        destination = (
            DFP_DIR /
            f"dfp_cia_aberta_{year}.zip"
        )

    elif document_type == "ITR":

        url = itr_url(year)

        destination = (
            ITR_DIR /
            f"itr_cia_aberta_{year}.zip"
        )

    elif document_type == "FCA":

        url = fca_url(year)

        destination = (
            FCA_DIR /
            f"fca_cia_aberta_{year}.zip"
        )

    else:

        raise ValueError(
            f"Tipo inválido: {document_type}"
        )

    if not remote_exists(url):

        return {
            "document_type": document_type,
            "year": year,
            "available": False,
            "url": url,
        }

    print(
        f"Atualizando {document_type} {year}..."
    )

    result = download_atomic(
        url,
        destination,
    )

    result.update({
        "document_type": document_type,
        "year": year,
        "available": True,
    })

    print(
        f"✓ {document_type} {year}"
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
        if x.get("available")
    ]

    available_itr = [
        x["year"]
        for x in itr_results
        if x.get("available")
    ]

    available_fca = [
        x["year"]
        for x in fca_results
        if x.get("available")
    ]

    manifest = {
        "engine": "B3_INVESTMENT_ENGINE",
        "layer": "LIVE_CVM_DATA",
        "generated_at_utc": utc_now_iso(),

        "methodology": {
            "status": "FROZEN_UNCHANGED",
            "quality_engine_modified": False,
            "valuation_modified": False,
            "technical_engine_modified": False,
        },

        "source": {
            "provider": "CVM",
            "official_base": CVM_BASE,
        },

        "registry": registry,

        "dfp": {
            "first_requested_year": (
                FIRST_STUDY_YEAR
            ),
            "latest_available_year": (
                max(available_dfp)
                if available_dfp
                else None
            ),
            "files": dfp_results,
        },

        "itr": {
            "first_requested_year": (
                FIRST_STUDY_YEAR
            ),
            "latest_available_year": (
                max(available_itr)
                if available_itr
                else None
            ),
            "files": itr_results,
        },

        "fca": {
            "first_requested_year": (
                FIRST_STUDY_YEAR
            ),
            "latest_available_year": (
                max(available_fca)
                if available_fca
                else None
            ),
            "files": fca_results,
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

    # O ITR deve acompanhar o exercício corrente
    # quando o arquivo do ano corrente já existir.
    if latest_itr < current_year:

        raise CVMDataError(
            "DATA_STALE: "
            f"último ITR disponível = {latest_itr}; "
            f"ano corrente = {current_year}."
        )

    # Para DFP, o arquivo do ano corrente pode existir
    # ainda incompleto no decorrer do exercício.
    # Aqui verificamos disponibilidade, não confundimos
    # presença do ZIP com fechamento anual completo.
    if latest_dfp < current_year - 1:

        raise CVMDataError(
            "DATA_STALE: "
            f"último DFP disponível = {latest_dfp}; "
            f"ano corrente = {current_year}."
        )


# ============================================================
# EXECUÇÃO
# ============================================================

def main() -> int:

    print("=" * 80)
    print("B3 INVESTMENT ENGINE")
    print("ATUALIZAÇÃO OFICIAL CVM")
    print("=" * 80)

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
        f"{years[0]}–{years[-1]}"
    )

    print(
        "Metodologia fundamental: "
        "CONGELADA / NÃO ALTERADA"
    )

    # --------------------------------------------------------
    # Cadastro
    # --------------------------------------------------------

    registry = update_company_registry()

    # --------------------------------------------------------
    # DFP
    # --------------------------------------------------------

    print("\n" + "-" * 80)
    print("DFP")
    print("-" * 80)

    dfp_results = []

    for year in years:

        result = update_year_file(
            "DFP",
            year,
        )

        dfp_results.append(result)

        if not result["available"]:
            print(
                f"- DFP {year}: "
                "não disponível"
            )

    # --------------------------------------------------------
    # ITR
    # --------------------------------------------------------

    print("\n" + "-" * 80)
    print("ITR")
    print("-" * 80)

    itr_results = []

    for year in years:

        result = update_year_file(
            "ITR",
            year,
        )

        itr_results.append(result)

        if not result["available"]:
            print(
                f"- ITR {year}: "
                "não disponível"
            )

    # --------------------------------------------------------
    # FCA
    # --------------------------------------------------------

    print("\n" + "-" * 80)
    print("FCA")
    print("-" * 80)

    fca_results = []

    for year in years:

        result = update_year_file(
            "FCA",
            year,
        )

        fca_results.append(result)

        if not result["available"]:
            print(
                f"- FCA {year}: "
                "não disponível"
            )

    # --------------------------------------------------------
    # Manifesto
    # --------------------------------------------------------

    manifest = write_manifest(
        registry,
        dfp_results,
        itr_results,
        fca_results,
    )

    # --------------------------------------------------------
    # Freshness
    # --------------------------------------------------------

    validate_current_data(
        manifest,
        current_year,
    )

    print("\n" + "=" * 80)
    print("ATUALIZAÇÃO CVM CONCLUÍDA")
    print("=" * 80)

    print(
        "Último DFP disponível:",
        manifest["dfp"]
        ["latest_available_year"],
    )

    print(
        "Último ITR disponível:",
        manifest["itr"]
        ["latest_available_year"],
    )

    print(
        "Último FCA disponível:",
        manifest["fca"]
        ["latest_available_year"],
    )

    print(
        "Manifesto:",
        MANIFEST_PATH,
    )

    print(
        "\nQuality Engine alterado: NÃO"
    )

    print(
        "Valuation alterado: NÃO"
    )

    print(
        "Technical Engine alterado: NÃO"
    )

    print("=" * 80)

    return 0


if __name__ == "__main__":

    try:

        sys.exit(main())

    except CVMDataError as exc:

        print(
            f"\nERRO CVM: {exc}",
            file=sys.stderr,
        )

        sys.exit(2)

    except Exception as exc:

        print(
            f"\nERRO NÃO PREVISTO: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)
