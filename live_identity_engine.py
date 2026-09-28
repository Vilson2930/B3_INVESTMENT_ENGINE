"""
B3 INVESTMENT ENGINE
LIVE IDENTITY ENGINE V1

Função:
    Construir a identidade CVM atualizada para o universo DFP disponível
    no momento da execução.

Metodologia:
    Reprodução operacional da lógica validada na Cell6 original.

IMPORTANTE:
    - Não calcula Quality Score.
    - Não calcula Valuation.
    - Não elimina empresas.
    - Não altera classificação setorial.
    - Não altera os motores V1 validados.
    - CD_CVM continua sendo a identidade oficial.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURAÇÃO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

LIVE_CVM_DIR = (
    PROJECT_ROOT
    / "data"
    / "live"
    / "cvm"
)

CADASTRO_CVM = (
    LIVE_CVM_DIR
    / "cad_cia_aberta.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "live"
    / "processed"
)

OUTPUT_IDENTITY = (
    OUTPUT_DIR
    / "cvm_company_identity_master.csv"
)

OUTPUT_NAME_HISTORY = (
    OUTPUT_DIR
    / "cvm_company_name_history.csv"
)


# ============================================================
# EXCEÇÃO
# ============================================================

class LiveIdentityError(RuntimeError):
    """Erro na construção da identidade CVM live."""


# ============================================================
# UTILITÁRIOS
# ============================================================

def _validate_dre(dre: pd.DataFrame) -> None:
    """
    Valida somente os campos necessários pela Cell6 original.
    """

    required = {
        "CD_CVM",
        "DENOM_CIA",
        "ANO_FONTE",
        "DT_REFER",
    }

    missing = sorted(
        required.difference(dre.columns)
    )

    if missing:
        raise LiveIdentityError(
            "DRE sem campos obrigatórios para identidade CVM: "
            + ", ".join(missing)
        )


def _read_csv_cvm(path: Path) -> pd.DataFrame:
    """
    Lê cadastro oficial CVM usando o mesmo padrão da Cell6.
    """

    if not path.exists():
        raise LiveIdentityError(
            f"Cadastro oficial CVM não encontrado: {path}"
        )

    try:
        return pd.read_csv(
            path,
            sep=";",
            encoding="latin-1",
            low_memory=False,
        )

    except Exception as exc:
        raise LiveIdentityError(
            f"Falha ao ler cadastro oficial CVM: {path}"
        ) from exc


# ============================================================
# BASE DE IDENTIDADE — CELL6 / ITEM 3
# ============================================================

def build_identity_base(
    dre: pd.DataFrame,
) -> pd.DataFrame:
    """
    Reprodução da construção de base_identidade da Cell6.
    """

    _validate_dre(dre)

    base_identidade = (
        dre[
            [
                "CD_CVM",
                "DENOM_CIA",
                "ANO_FONTE",
                "DT_REFER",
            ]
        ]
        .copy()
    )

    base_identidade["CD_CVM"] = pd.to_numeric(
        base_identidade["CD_CVM"],
        errors="coerce",
    )

    base_identidade = (
        base_identidade
        .dropna(
            subset=["CD_CVM"]
        )
    )

    base_identidade["CD_CVM"] = (
        base_identidade["CD_CVM"]
        .astype("int64")
    )

    base_identidade["DENOM_CIA"] = (
        base_identidade["DENOM_CIA"]
        .astype(str)
        .str.strip()
    )

    base_identidade["DT_REFER"] = pd.to_datetime(
        base_identidade["DT_REFER"],
        errors="coerce",
    )

    base_identidade = (
        base_identidade
        .drop_duplicates(
            [
                "CD_CVM",
                "DENOM_CIA",
                "ANO_FONTE",
                "DT_REFER",
            ]
        )
    )

    return base_identidade


# ============================================================
# HISTÓRICO DE DENOMINAÇÕES — CELL6 / ITEM 5
# ============================================================

def build_name_history(
    base_identidade: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    nomes_unicos = (
        base_identidade[
            [
                "CD_CVM",
                "DENOM_CIA",
            ]
        ]
        .drop_duplicates()
    )

    qtd_nomes = (
        nomes_unicos
        .groupby("CD_CVM")
        .size()
        .reset_index(
            name="QTD_DENOMINACOES"
        )
    )

    nomes_historicos = (
        nomes_unicos
        .groupby("CD_CVM")[
            "DENOM_CIA"
        ]
        .agg(
            lambda x:
            " | ".join(
                sorted(
                    set(
                        str(v).strip()
                        for v in x
                        if str(v).strip()
                    )
                )
            )
        )
        .reset_index(
            name="DENOMINACOES_HISTORICAS"
        )
    )

    return qtd_nomes, nomes_historicos


# ============================================================
# DENOMINAÇÃO MAIS RECENTE — CELL6 / ITEM 6
# ============================================================

def build_latest_dfp_name(
    base_identidade: pd.DataFrame,
) -> pd.DataFrame:

    return (
        base_identidade
        .sort_values(
            [
                "CD_CVM",
                "DT_REFER",
                "ANO_FONTE",
            ]
        )
        .drop_duplicates(
            subset=["CD_CVM"],
            keep="last",
        )
        [
            [
                "CD_CVM",
                "DENOM_CIA",
                "DT_REFER",
                "ANO_FONTE",
            ]
        ]
        .rename(
            columns={
                "DENOM_CIA":
                    "DENOM_CIA_DFP_RECENTE",

                "DT_REFER":
                    "ULTIMA_DT_REFER_DFP",

                "ANO_FONTE":
                    "ULTIMO_ANO_DFP",
            }
        )
    )


# ============================================================
# COBERTURA HISTÓRICA — CELL6 / ITEM 7
# ============================================================

def build_dfp_coverage(
    base_identidade: pd.DataFrame,
) -> pd.DataFrame:

    return (
        base_identidade
        .groupby("CD_CVM")
        .agg(
            PRIMEIRO_ANO_DFP=(
                "ANO_FONTE",
                "min",
            ),

            ULTIMO_ANO_DFP_AUDITADO=(
                "ANO_FONTE",
                "max",
            ),

            QTD_ANOS_DFP=(
                "ANO_FONTE",
                "nunique",
            ),
        )
        .reset_index()
    )


# ============================================================
# MASTER INICIAL — CELL6 / ITEM 8
# ============================================================

def build_initial_identity_master(
    base_identidade: pd.DataFrame,
) -> pd.DataFrame:

    qtd_nomes, nomes_historicos = (
        build_name_history(
            base_identidade
        )
    )

    nome_atual_dfp = (
        build_latest_dfp_name(
            base_identidade
        )
    )

    cobertura_dfp = (
        build_dfp_coverage(
            base_identidade
        )
    )

    identidade = (
        nome_atual_dfp
        .merge(
            qtd_nomes,
            on="CD_CVM",
            how="left",
        )
        .merge(
            nomes_historicos,
            on="CD_CVM",
            how="left",
        )
        .merge(
            cobertura_dfp,
            on="CD_CVM",
            how="left",
        )
    )

    identidade[
        "MUDOU_DENOMINACAO"
    ] = (
        identidade[
            "QTD_DENOMINACOES"
        ] > 1
    )

    return identidade


# ============================================================
# CADASTRO OFICIAL CVM — CELL6 / ITENS 10–15
# ============================================================

def prepare_official_registry(
    cadastro_cvm: pd.DataFrame,
) -> pd.DataFrame:

    if "CD_CVM" not in cadastro_cvm.columns:
        raise LiveIdentityError(
            "Campo CD_CVM não encontrado no cadastro oficial CVM."
        )

    cadastro_cvm = cadastro_cvm.copy()

    cadastro_cvm["CD_CVM"] = pd.to_numeric(
        cadastro_cvm["CD_CVM"],
        errors="coerce",
    )

    cadastro_cvm = (
        cadastro_cvm
        .dropna(
            subset=["CD_CVM"]
        )
    )

    cadastro_cvm["CD_CVM"] = (
        cadastro_cvm["CD_CVM"]
        .astype("int64")
    )

    cad = cadastro_cvm.copy()

    campos_data = [
        "DT_REG",
        "DT_INI_SIT",
        "DT_CONST",
        "DT_CANCEL",
    ]

    for coluna in campos_data:

        if coluna in cad.columns:

            cad[coluna] = pd.to_datetime(
                cad[coluna],
                errors="coerce",
            )

    if "DT_INI_SIT" in cad.columns:

        cad = (
            cad
            .sort_values(
                [
                    "CD_CVM",
                    "DT_INI_SIT",
                ],
                na_position="first",
            )
        )

    else:

        cad = (
            cad
            .sort_values(
                "CD_CVM"
            )
        )

    cad_atual = (
        cad
        .drop_duplicates(
            subset=["CD_CVM"],
            keep="last",
        )
        .copy()
    )

    campos_interesse = [
        "CD_CVM",
        "CNPJ_CIA",
        "DENOM_SOCIAL",
        "DENOM_COMERC",
        "SETOR_ATIV",
        "TP_MERC",
        "CATEG_REG",
        "SIT",
        "DT_REG",
        "DT_INI_SIT",
        "DT_CANCEL",
        "PAIS",
        "UF",
    ]

    campos_existentes = [
        coluna
        for coluna in campos_interesse
        if coluna in cad_atual.columns
    ]

    cad_reduzido = (
        cad_atual[
            campos_existentes
        ]
        .copy()
    )

    renomear = {
        coluna:
            "CAD_" + coluna

        for coluna
        in cad_reduzido.columns

        if coluna != "CD_CVM"
    }

    cad_reduzido = (
        cad_reduzido
        .rename(
            columns=renomear
        )
    )

    return cad_reduzido


# ============================================================
# MERGE DFP + CADASTRO — CELL6 / ITENS 16–17
# ============================================================

def merge_registry(
    identidade: pd.DataFrame,
    cad_reduzido: pd.DataFrame,
) -> pd.DataFrame:

    resultado = (
        identidade
        .merge(
            cad_reduzido,
            on="CD_CVM",
            how="left",
            indicator="_MERGE_CADASTRO",
        )
    )

    resultado[
        "CADASTRO_LOCALIZADO"
    ] = (
        resultado[
            "_MERGE_CADASTRO"
        ].eq("both")
    )

    resultado = (
        resultado
        .drop(
            columns=[
                "_MERGE_CADASTRO"
            ]
        )
    )

    if (
        "CAD_DENOM_SOCIAL"
        in resultado.columns
    ):

        denom_cadastro = (
            resultado[
                "CAD_DENOM_SOCIAL"
            ]
            .replace(
                r"^\s*$",
                np.nan,
                regex=True,
            )
        )

        resultado[
            "DENOM_CIA_ATUAL"
        ] = (
            denom_cadastro
            .fillna(
                resultado[
                    "DENOM_CIA_DFP_RECENTE"
                ]
            )
        )

    else:

        resultado[
            "DENOM_CIA_ATUAL"
        ] = (
            resultado[
                "DENOM_CIA_DFP_RECENTE"
            ]
        )

    return resultado


# ============================================================
# AUDITORIA
# ============================================================

def audit_identity(
    identidade: pd.DataFrame,
) -> dict:

    if "CD_CVM" not in identidade.columns:
        raise LiveIdentityError(
            "Master final sem CD_CVM."
        )

    total = len(identidade)

    unique = (
        identidade[
            "CD_CVM"
        ]
        .nunique()
    )

    duplicates = (
        identidade[
            "CD_CVM"
        ]
        .duplicated()
        .sum()
    )

    if duplicates != 0:
        raise LiveIdentityError(
            "Identidade CVM inválida: "
            f"{duplicates} duplicidade(s) de CD_CVM."
        )

    if total != unique:
        raise LiveIdentityError(
            "Identidade CVM inválida: "
            "quantidade de linhas diferente "
            "da quantidade de CD_CVM únicos."
        )

    cadastro_localizado = None

    if (
        "CADASTRO_LOCALIZADO"
        in identidade.columns
    ):

        cadastro_localizado = int(
            identidade[
                "CADASTRO_LOCALIZADO"
            ].sum()
        )

    return {
        "companies": total,
        "unique_cd_cvm": unique,
        "duplicate_cd_cvm": int(
            duplicates
        ),
        "registry_found": cadastro_localizado,
        "status": "VALIDATED",
    }


# ============================================================
# ENGINE
# ============================================================

def run_live_identity_engine(
    dre: pd.DataFrame,
    cadastro_path: Path | str = CADASTRO_CVM,
    save_outputs: bool = True,
) -> pd.DataFrame:
    """
    Executa a lógica de identidade da Cell6 sobre dados atuais.

    Nenhuma empresa é eliminada.
    """

    cadastro_path = Path(
        cadastro_path
    )

    base_identidade = (
        build_identity_base(
            dre
        )
    )

    identidade = (
        build_initial_identity_master(
            base_identidade
        )
    )

    cadastro_cvm = (
        _read_csv_cvm(
            cadastro_path
        )
    )

    cad_reduzido = (
        prepare_official_registry(
            cadastro_cvm
        )
    )

    identidade = (
        merge_registry(
            identidade,
            cad_reduzido,
        )
    )

    audit = (
        audit_identity(
            identidade
        )
    )

    if save_outputs:

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        identidade.to_csv(
            OUTPUT_IDENTITY,
            index=False,
            encoding="utf-8-sig",
        )

        base_identidade[
            [
                "CD_CVM",
                "DENOM_CIA",
                "ANO_FONTE",
                "DT_REFER",
            ]
        ].to_csv(
            OUTPUT_NAME_HISTORY,
            index=False,
            encoding="utf-8-sig",
        )

    print("=" * 72)
    print("LIVE IDENTITY ENGINE V1")
    print("=" * 72)

    print(
        "Companhias DFP:",
        audit["companies"],
    )

    print(
        "CD_CVM únicos:",
        audit["unique_cd_cvm"],
    )

    print(
        "Duplicidades:",
        audit["duplicate_cd_cvm"],
    )

    print(
        "Cadastro CVM localizado:",
        audit["registry_found"],
    )

    print(
        "Identidade:",
        audit["status"],
    )

    print()
    print("Quality Engine alterado: NÃO")
    print("Valuation Engine alterado: NÃO")
    print("Sector Engine alterado: NÃO")
    print("Technical Engine alterado: NÃO")
    print("Empresas eliminadas nesta etapa: NÃO")
    print("Identidade oficial: CD_CVM")
    print("=" * 72)

    return identidade


# ============================================================
# EXPORTS
# ============================================================

__all__: Iterable[str] = [
    "LiveIdentityError",
    "build_identity_base",
    "build_name_history",
    "build_latest_dfp_name",
    "build_dfp_coverage",
    "build_initial_identity_master",
    "prepare_official_registry",
    "merge_registry",
    "audit_identity",
    "run_live_identity_engine",
]
