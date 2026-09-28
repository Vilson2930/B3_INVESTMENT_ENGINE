"""
B3 INVESTMENT ENGINE
BUILD LIVE FUNDAMENTAL INPUT — V1

OBJETIVO
-------
Construir a entrada fundamental de PRODUÇÃO utilizando dados atualizados,
preservando integralmente a metodologia validada no estudo original.

ARQUITETURA CONGELADA
---------------------
CVM
→ arquitetura setorial V1
→ indicadores fundamentais V1
→ Quality Engine V1
→ Quality Gate >= 60
→ investibilidade B3
→ mínimo 10 anos
→ liquidez média diária >= R$ 6 milhões
→ Valuation V1
→ 70% Quality + 30% Valuation
→ ranking fundamental

PRINCÍPIO CENTRAL
-----------------
A metodologia não muda.
Os dados mudam.

Este módulo NÃO substitui build_fundamental_input.py.
O arquivo antigo permanece como benchmark/regressão do estudo original.

Nenhuma regra metodológica pode ser alterada silenciosamente.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# 1. CAMINHOS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"

LIVE_DIR = DATA_DIR / "live"
CVM_DIR = LIVE_DIR / "cvm"

OUTPUT_DIR = LIVE_DIR / "fundamental"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CVM_MANIFEST = CVM_DIR / "cvm_manifest.json"

OUTPUT_FILE = OUTPUT_DIR / "fundamental_input_live.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "fundamental_live_manifest.json"


# ============================================================
# 2. METODOLOGIA V1 — CONGELADA
# ============================================================

METHODOLOGY_VERSION = "B3_FUNDAMENTAL_V1"

QUALITY_GATE = 60.0

MIN_HISTORY_YEARS = 10.0

MIN_AVG_DAILY_LIQUIDITY_BRL = 6_000_000.0

QUALITY_WEIGHT = 0.70

VALUATION_WEIGHT = 0.30


# ============================================================
# 3. ARQUITETURA SETORIAL V1 — MOTORES OFICIAIS
# ============================================================

VALID_SECTOR_ENGINES = {
    "OPERACIONAL",
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
    "UTILITY",
    "COMMODITY",
    "IMOBILIARIO",
    "AMBIENTAL_RESIDUOS",
    "AUDITAR",
}


# ============================================================
# 4. POLÍTICA DE PRODUÇÃO
# ============================================================

TECHNICAL_CHANGES_QUALITY = False
TECHNICAL_RESCUES_FAILED_FUNDAMENTAL = False
TECHNICAL_PARTICIPATES_IN_FUNDAMENTAL_RANKING = False

VALUATION_BEFORE_QUALITY = False

ALLOW_METHODOLOGY_FALLBACK = False
ALLOW_SYNTHETIC_DATA = False
ALLOW_MISSING_CVM_MANIFEST = False


# ============================================================
# 5. EXCEÇÕES
# ============================================================

class LiveFundamentalError(RuntimeError):
    """Erro que impede geração segura do fundamental live."""


class DataInsufficientError(LiveFundamentalError):
    """Dados insuficientes para executar metodologia V1."""


class DataStaleError(LiveFundamentalError):
    """Dados oficiais estão desatualizados."""


class MethodologyIntegrityError(LiveFundamentalError):
    """Alguma regra congelada da metodologia foi violada."""


# ============================================================
# 6. UTILITÁRIOS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json_atomic(data: dict, path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")

    with temp.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    temp.replace(path)


def write_csv_atomic(df: pd.DataFrame, path: Path) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")

    df.to_csv(
        temp,
        index=False,
        encoding="utf-8-sig",
    )

    temp.replace(path)


# ============================================================
# 7. AUDITORIA DA METODOLOGIA
# ============================================================

def audit_frozen_methodology() -> None:

    errors = []

    if QUALITY_GATE != 60.0:
        errors.append("QUALITY_GATE")

    if MIN_HISTORY_YEARS != 10.0:
        errors.append("MIN_HISTORY_YEARS")

    if MIN_AVG_DAILY_LIQUIDITY_BRL != 6_000_000.0:
        errors.append("MIN_AVG_DAILY_LIQUIDITY_BRL")

    if QUALITY_WEIGHT != 0.70:
        errors.append("QUALITY_WEIGHT")

    if VALUATION_WEIGHT != 0.30:
        errors.append("VALUATION_WEIGHT")

    if abs(
        QUALITY_WEIGHT + VALUATION_WEIGHT - 1.0
    ) > 1e-12:
        errors.append("FUNDAMENTAL_WEIGHTS")

    if VALUATION_BEFORE_QUALITY:
        errors.append("VALUATION_BEFORE_QUALITY")

    if TECHNICAL_CHANGES_QUALITY:
        errors.append("TECHNICAL_CHANGES_QUALITY")

    if TECHNICAL_RESCUES_FAILED_FUNDAMENTAL:
        errors.append(
            "TECHNICAL_RESCUES_FAILED_FUNDAMENTAL"
        )

    if TECHNICAL_PARTICIPATES_IN_FUNDAMENTAL_RANKING:
        errors.append(
            "TECHNICAL_PARTICIPATES_IN_FUNDAMENTAL_RANKING"
        )

    if ALLOW_METHODOLOGY_FALLBACK:
        errors.append("ALLOW_METHODOLOGY_FALLBACK")

    if ALLOW_SYNTHETIC_DATA:
        errors.append("ALLOW_SYNTHETIC_DATA")

    if errors:
        raise MethodologyIntegrityError(
            "Metodologia V1 alterada: "
            + ", ".join(errors)
        )


# ============================================================
# 8. AUDITORIA DOS DADOS CVM
# ============================================================

def audit_cvm_data() -> dict:

    if not CVM_MANIFEST.exists():

        if ALLOW_MISSING_CVM_MANIFEST:
            return {}

        raise DataInsufficientError(
            f"Manifest CVM não encontrado: {CVM_MANIFEST}"
        )

    manifest = read_json(CVM_MANIFEST)

    registry = CVM_DIR / "cad_cia_aberta.csv"

    if not registry.exists():
        raise DataInsufficientError(
            "Cadastro oficial CVM não encontrado."
        )

    dfp_dir = CVM_DIR / "dfp"
    itr_dir = CVM_DIR / "itr"

    if not dfp_dir.exists():
        raise DataInsufficientError(
            "Diretório DFP não encontrado."
        )

    if not itr_dir.exists():
        raise DataInsufficientError(
            "Diretório ITR não encontrado."
        )

    dfp_files = sorted(
        dfp_dir.glob("dfp_cia_aberta_*.zip")
    )

    itr_files = sorted(
        itr_dir.glob("itr_cia_aberta_*.zip")
    )

    if not dfp_files:
        raise DataInsufficientError(
            "Nenhum arquivo DFP disponível."
        )

    if not itr_files:
        raise DataInsufficientError(
            "Nenhum arquivo ITR disponível."
        )

    return manifest


# ============================================================
# 9. VALIDAÇÃO DA SAÍDA LIVE
# ============================================================

def validate_live_output(df: pd.DataFrame) -> None:

    required = {
        "TICKER",
        "QUALITY_SCORE",
        "HISTORY_YEARS",
        "AVG_DAILY_LIQUIDITY_BRL",
        "VALUATION_SCORE",
    }

    missing = required - set(df.columns)

    if missing:
        raise DataInsufficientError(
            "Saída live sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    if df.empty:
        raise DataInsufficientError(
            "Saída fundamental live vazia."
        )

    if df["TICKER"].isna().any():
        raise DataInsufficientError(
            "Existem empresas sem ticker na saída live."
        )

    if df["TICKER"].duplicated().any():
        duplicated = (
            df.loc[
                df["TICKER"].duplicated(
                    keep=False
                ),
                "TICKER",
            ]
            .astype(str)
            .tolist()
        )

        raise MethodologyIntegrityError(
            "Tickers duplicados na saída live: "
            + ", ".join(duplicated[:20])
        )

    quality = pd.to_numeric(
        df["QUALITY_SCORE"],
        errors="coerce",
    )

    history = pd.to_numeric(
        df["HISTORY_YEARS"],
        errors="coerce",
    )

    liquidity = pd.to_numeric(
        df["AVG_DAILY_LIQUIDITY_BRL"],
        errors="coerce",
    )

    if quality.isna().any():
        raise DataInsufficientError(
            "QUALITY_SCORE inválido."
        )

    if history.isna().any():
        raise DataInsufficientError(
            "HISTORY_YEARS inválido."
        )

    if liquidity.isna().any():
        raise DataInsufficientError(
            "AVG_DAILY_LIQUIDITY_BRL inválida."
        )

    if (quality < QUALITY_GATE).any():
        raise MethodologyIntegrityError(
            "Empresa abaixo do Quality Gate "
            "entrou no universo live."
        )

    if (history < MIN_HISTORY_YEARS).any():
        raise MethodologyIntegrityError(
            "Empresa com menos de 10 anos "
            "entrou no universo live."
        )

    if (
        liquidity
        < MIN_AVG_DAILY_LIQUIDITY_BRL
    ).any():
        raise MethodologyIntegrityError(
            "Empresa abaixo de R$ 6 milhões/dia "
            "entrou no universo live."
        )


# ============================================================
# 10. CÁLCULO DO SCORE FUNDAMENTAL
# ============================================================

def calculate_fundamental_score(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = df.copy()

    result["QUALITY_SCORE"] = pd.to_numeric(
        result["QUALITY_SCORE"],
        errors="coerce",
    )

    result["VALUATION_SCORE"] = pd.to_numeric(
        result["VALUATION_SCORE"],
        errors="coerce",
    )

    result["FUNDAMENTAL_SCORE"] = pd.NA

    mask = (
        result["QUALITY_SCORE"].notna()
        &
        result["VALUATION_SCORE"].notna()
    )

    result.loc[
        mask,
        "FUNDAMENTAL_SCORE",
    ] = (
        QUALITY_WEIGHT
        * result.loc[
            mask,
            "QUALITY_SCORE",
        ]
        +
        VALUATION_WEIGHT
        * result.loc[
            mask,
            "VALUATION_SCORE",
        ]
    )

    result["FUNDAMENTAL_SCORE"] = pd.to_numeric(
        result["FUNDAMENTAL_SCORE"],
        errors="coerce",
    )

    return result


# ============================================================
# 11. CONSTRUÇÃO LIVE
# ============================================================

def build_live_fundamental_input() -> pd.DataFrame:

    print("=" * 72)
    print("B3 INVESTMENT ENGINE")
    print("BUILD LIVE FUNDAMENTAL INPUT — V1")
    print("=" * 72)

    print("\n[1/5] Auditando metodologia congelada...")

    audit_frozen_methodology()

    print("✓ Metodologia V1 preservada.")

    print("\n[2/5] Auditando dados oficiais CVM...")

    cvm_manifest = audit_cvm_data()

    print("✓ Estrutura CVM disponível.")

    print("\n[3/5] Preparando execução fundamental LIVE...")

    # ========================================================
    # TRAVA DE FIDELIDADE
    # ========================================================
    #
    # A coleta CVM já está automatizada.
    #
    # Entretanto, este arquivo NÃO pode reconstruir
    # silenciosamente Quality/Valuation por aproximação.
    #
    # A implementação dos módulos abaixo deve reproduzir
    # literalmente os motores recuperados do estudo original:
    #
    # 1. arquitetura setorial Cells 8–12
    # 2. indicadores fundamentais Cell17
    # 3. Quality Engine Cell18
    # 4. investibilidade Cell19
    # 5. Valuation Cell33C
    #
    # Enquanto esses componentes não estiverem conectados
    # neste módulo de produção, a execução deve PARAR.
    #
    # Isso é intencional.
    # É preferível DATA_INSUFFICIENT a produzir um ranking
    # usando metodologia diferente da validada.
    # ========================================================

    raise DataInsufficientError(
        "LIVE FUNDAMENTAL ainda não conectado aos motores "
        "V1 recuperados. Dados CVM foram atualizados, mas "
        "nenhum Quality Score ou Valuation será aproximado. "
        "Execução interrompida para preservar integralmente "
        "a metodologia original."
    )


# ============================================================
# 12. MANIFEST DE EXECUÇÃO
# ============================================================

def build_manifest(
    status: str,
    error: str | None = None,
) -> dict:

    return {
        "engine": "B3_INVESTMENT_ENGINE",
        "module": "build_live_fundamental_input",
        "methodology_version": METHODOLOGY_VERSION,
        "generated_at_utc": utc_now().isoformat(),
        "status": status,
        "error": error,
        "methodology": {
            "quality_gate": QUALITY_GATE,
            "minimum_history_years": (
                MIN_HISTORY_YEARS
            ),
            "minimum_avg_daily_liquidity_brl": (
                MIN_AVG_DAILY_LIQUIDITY_BRL
            ),
            "quality_weight": QUALITY_WEIGHT,
            "valuation_weight": VALUATION_WEIGHT,
            "valuation_after_quality": True,
            "technical_changes_quality": (
                TECHNICAL_CHANGES_QUALITY
            ),
            "technical_rescues_failed_fundamental": (
                TECHNICAL_RESCUES_FAILED_FUNDAMENTAL
            ),
            "technical_participates_in_ranking": (
                TECHNICAL_PARTICIPATES_IN_FUNDAMENTAL_RANKING
            ),
        },
        "sector_engines": sorted(
            VALID_SECTOR_ENGINES
        ),
        "output_file": str(OUTPUT_FILE),
    }


# ============================================================
# 13. MAIN
# ============================================================

def main() -> int:

    try:

        df = build_live_fundamental_input()

        validate_live_output(df)

        df = calculate_fundamental_score(df)

        write_csv_atomic(
            df,
            OUTPUT_FILE,
        )

        manifest = build_manifest(
            status="OK"
        )

        write_json_atomic(
            manifest,
            OUTPUT_MANIFEST,
        )

        print("\n" + "=" * 72)
        print("LIVE FUNDAMENTAL CONCLUÍDO")
        print("=" * 72)

        print(
            "Empresas:",
            len(df),
        )

        print(
            "Com valuation:",
            int(
                df[
                    "VALUATION_SCORE"
                ].notna().sum()
            ),
        )

        print(
            "Pendentes de valuation:",
            int(
                df[
                    "VALUATION_SCORE"
                ].isna().sum()
            ),
        )

        print(
            "Arquivo:",
            OUTPUT_FILE,
        )

        return 0

    except DataStaleError as exc:

        manifest = build_manifest(
            status="DATA_STALE",
            error=str(exc),
        )

        write_json_atomic(
            manifest,
            OUTPUT_MANIFEST,
        )

        print(
            f"\nDATA_STALE: {exc}",
            file=sys.stderr,
        )

        return 2

    except DataInsufficientError as exc:

        manifest = build_manifest(
            status="DATA_INSUFFICIENT",
            error=str(exc),
        )

        write_json_atomic(
            manifest,
            OUTPUT_MANIFEST,
        )

        print(
            f"\nDATA_INSUFFICIENT: {exc}",
            file=sys.stderr,
        )

        return 3

    except MethodologyIntegrityError as exc:

        manifest = build_manifest(
            status="METHODOLOGY_INTEGRITY_ERROR",
            error=str(exc),
        )

        write_json_atomic(
            manifest,
            OUTPUT_MANIFEST,
        )

        print(
            f"\nMETHODOLOGY_INTEGRITY_ERROR: {exc}",
            file=sys.stderr,
        )

        return 4

    except Exception as exc:

        manifest = build_manifest(
            status="ERROR",
            error=repr(exc),
        )

        write_json_atomic(
            manifest,
            OUTPUT_MANIFEST,
        )

        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
