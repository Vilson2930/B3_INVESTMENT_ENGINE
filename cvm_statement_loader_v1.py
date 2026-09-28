"""
B3 INVESTMENT ENGINE
CVM STATEMENT LOADER V1

OBJETIVO
--------
Ler os ZIPs oficiais DFP e ITR já baixados por
update_cvm_data.py.

PRINCÍPIO DE FIDELIDADE
-----------------------
O estudo histórico utilizou demonstrativos CONSOLIDADOS:

BPA_con
BPP_con
DRE_con
DFC_MD_con
DFC_MI_con

Este módulo mantém exatamente essa escolha.

IMPORTANTE
----------
DFP e ITR NÃO são misturados.

DFP:
    alimenta a série histórica anual validada.

ITR:
    fica disponível separadamente para a futura camada
    de atualização corrente/intraperíodo.

Isso impede que um trimestre seja tratado como se fosse
um exercício anual completo.
"""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd


# ============================================================
# 1. CONFIGURAÇÃO
# ============================================================

ROOT = Path(__file__).resolve().parent

CVM_ROOT = (
    ROOT
    / "data"
    / "live"
    / "cvm"
)

DFP_DIR = CVM_ROOT / "dfp"
ITR_DIR = CVM_ROOT / "itr"


STATEMENT_MARKERS = {
    "BPA": "BPA_con",
    "BPP": "BPP_con",
    "DRE": "DRE_con",
    "DFC_MD": "DFC_MD_con",
    "DFC_MI": "DFC_MI_con",
}


REQUIRED_BALANCE_COLUMNS = {
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "ORDEM_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
}


REQUIRED_RESULT_COLUMNS = (
    REQUIRED_BALANCE_COLUMNS
    |
    {
        "DT_INI_EXERC",
    }
)


# ============================================================
# 2. EXCEÇÕES
# ============================================================

class CVMStatementLoaderError(
    RuntimeError
):
    pass


# ============================================================
# 3. LEITURA SEGURA DO CSV
# ============================================================

def read_csv_from_zip(
    zip_obj: ZipFile,
    member: str,
) -> pd.DataFrame:

    """
    Reprodução da leitura utilizada no estudo:

    sep=";"
    encoding="latin-1"
    low_memory=False
    """

    with zip_obj.open(member) as file:

        return pd.read_csv(
            file,
            sep=";",
            encoding="latin-1",
            low_memory=False,
        )


# ============================================================
# 4. LOCALIZAR UM DEMONSTRATIVO CONSOLIDADO
# ============================================================

def find_statement_member(
    members: list[str],
    marker: str,
) -> str | None:

    matches = [
        member
        for member in members
        if marker.lower()
        in member.lower()
        and member.lower().endswith(
            ".csv"
        )
    ]

    if not matches:
        return None

    # Segurança:
    # nunca selecionar versão "_ind_".

    consolidated = [
        member
        for member in matches
        if "_con_" in member.lower()
    ]

    if len(consolidated) == 1:
        return consolidated[0]

    if len(consolidated) > 1:

        raise CVMStatementLoaderError(
            "Mais de um demonstrativo "
            f"consolidado encontrado para "
            f"{marker}: {consolidated}"
        )

    return None


# ============================================================
# 5. SCHEMA
# ============================================================

def validate_statement_schema(
    df: pd.DataFrame,
    statement: str,
    dataset: str,
    year: int,
) -> None:

    if statement in {
        "DRE",
        "DFC_MD",
        "DFC_MI",
    }:
        required = (
            REQUIRED_RESULT_COLUMNS
        )

    else:
        required = (
            REQUIRED_BALANCE_COLUMNS
        )

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        raise CVMStatementLoaderError(
            f"{dataset} {year} "
            f"{statement}: colunas "
            "obrigatórias ausentes: "
            + ", ".join(
                sorted(missing)
            )
        )


# ============================================================
# 6. PREPARAÇÃO PADRÃO
# ============================================================

def prepare_loaded_statement(
    df: pd.DataFrame,
    dataset: str,
    year: int,
    statement: str,
    source_zip: Path,
    source_member: str,
) -> pd.DataFrame:

    x = df.copy()

    x["CD_CVM"] = pd.to_numeric(
        x["CD_CVM"],
        errors="coerce",
    )

    x["VL_CONTA"] = pd.to_numeric(
        x["VL_CONTA"],
        errors="coerce",
    )

    x["VERSAO"] = pd.to_numeric(
        x["VERSAO"],
        errors="coerce",
    )

    x["ANO"] = int(year)

    x["DATASET_CVM"] = dataset

    x["DEMONSTRATIVO"] = statement

    x["SOURCE_ZIP"] = (
        source_zip.name
    )

    x["SOURCE_MEMBER"] = (
        source_member
    )

    return x


# ============================================================
# 7. CARREGAR UM ZIP
# ============================================================

def load_one_zip(
    zip_path: Path,
    dataset: str,
    year: int,
) -> dict[str, pd.DataFrame]:

    if not zip_path.exists():

        raise CVMStatementLoaderError(
            f"Arquivo ausente: "
            f"{zip_path}"
        )

    try:

        with ZipFile(
            zip_path,
            "r",
        ) as z:

            bad_member = (
                z.testzip()
            )

            if bad_member is not None:

                raise (
                    CVMStatementLoaderError(
                        "ZIP corrompido: "
                        f"{zip_path.name}; "
                        f"membro={bad_member}"
                    )
                )

            members = z.namelist()

            result = {}

            for (
                statement,
                marker,
            ) in (
                STATEMENT_MARKERS.items()
            ):

                member = (
                    find_statement_member(
                        members,
                        marker,
                    )
                )

                # DFC_MD e DFC_MI podem não
                # existir para todas as situações.
                #
                # BPA/BPP/DRE são obrigatórios.

                if member is None:

                    if statement in {
                        "BPA",
                        "BPP",
                        "DRE",
                    }:

                        raise (
                            CVMStatementLoaderError(
                                f"{dataset} "
                                f"{year}: "
                                f"{statement} "
                                "consolidado "
                                "não encontrado."
                            )
                        )

                    result[
                        statement
                    ] = pd.DataFrame()

                    continue

                df = read_csv_from_zip(
                    z,
                    member,
                )

                validate_statement_schema(
                    df,
                    statement,
                    dataset,
                    year,
                )

                result[
                    statement
                ] = (
                    prepare_loaded_statement(
                        df,
                        dataset,
                        year,
                        statement,
                        zip_path,
                        member,
                    )
                )

            return result

    except BadZipFile as exc:

        raise CVMStatementLoaderError(
            f"ZIP inválido: {zip_path}"
        ) from exc


# ============================================================
# 8. DESCOBRIR ANOS DISPONÍVEIS
# ============================================================

def discover_available_years(
    directory: Path,
    dataset: str,
) -> list[int]:

    dataset = dataset.upper()

    prefix = (
        "dfp_cia_aberta_"
        if dataset == "DFP"
        else
        "itr_cia_aberta_"
    )

    years = []

    if not directory.exists():
        return years

    for path in directory.glob(
        f"{prefix}*.zip"
    ):

        stem = path.stem

        year_text = stem.replace(
            prefix,
            "",
        )

        if (
            len(year_text) == 4
            and year_text.isdigit()
        ):

            years.append(
                int(year_text)
            )

    return sorted(
        set(years)
    )


# ============================================================
# 9. CONCATENAÇÃO SEGURA
# ============================================================

def concat_statement_parts(
    parts: list[pd.DataFrame],
) -> pd.DataFrame:

    valid = [
        part
        for part in parts
        if part is not None
        and not part.empty
    ]

    if not valid:
        return pd.DataFrame()

    return pd.concat(
        valid,
        ignore_index=True,
        sort=False,
    )


# ============================================================
# 10. CARREGAR UM DATASET COMPLETO
# ============================================================

def load_dataset(
    dataset: str,
    directory: Path,
    years: list[int] | None = None,
) -> dict[str, pd.DataFrame]:

    dataset = dataset.upper()

    if dataset not in {
        "DFP",
        "ITR",
    }:

        raise ValueError(
            "dataset deve ser "
            "'DFP' ou 'ITR'."
        )

    if years is None:

        years = (
            discover_available_years(
                directory,
                dataset,
            )
        )

    years = sorted(
        set(
            int(year)
            for year in years
        )
    )

    if not years:

        raise CVMStatementLoaderError(
            f"Nenhum ZIP {dataset} "
            f"disponível em {directory}."
        )

    accumulator = {
        statement: []
        for statement
        in STATEMENT_MARKERS
    }

    for year in years:

        filename = (
            f"dfp_cia_aberta_{year}.zip"
            if dataset == "DFP"
            else
            f"itr_cia_aberta_{year}.zip"
        )

        zip_path = (
            directory
            / filename
        )

        loaded = load_one_zip(
            zip_path,
            dataset,
            year,
        )

        for statement in (
            STATEMENT_MARKERS
        ):

            accumulator[
                statement
            ].append(
                loaded[
                    statement
                ]
            )

    return {
        statement:
            concat_statement_parts(
                accumulator[
                    statement
                ]
            )
        for statement
        in STATEMENT_MARKERS
    }


# ============================================================
# 11. DFP — SÉRIE HISTÓRICA ANUAL
# ============================================================

def load_dfp_history(
    years: list[int] | None = None,
) -> dict[str, pd.DataFrame]:

    """
    Esta é a entrada compatível com
    cvm_fundamental_base_v1.py.

    DFP anual somente.
    """

    return load_dataset(
        dataset="DFP",
        directory=DFP_DIR,
        years=years,
    )


# ============================================================
# 12. ITR — CAMADA CORRENTE SEPARADA
# ============================================================

def load_itr_history(
    years: list[int] | None = None,
) -> dict[str, pd.DataFrame]:

    """
    Carrega ITR sem misturá-lo com DFP.

    O tratamento econômico do período
    corrente será feito em camada própria.
    """

    return load_dataset(
        dataset="ITR",
        directory=ITR_DIR,
        years=years,
    )


# ============================================================
# 13. AUDITORIA
# ============================================================

def audit_loaded_dataset(
    statements: dict[
        str,
        pd.DataFrame,
    ],
    dataset: str,
) -> pd.DataFrame:

    rows = []

    for statement in (
        STATEMENT_MARKERS
    ):

        df = statements.get(
            statement,
            pd.DataFrame(),
        )

        if df.empty:

            rows.append(
                {
                    "DATASET":
                        dataset,

                    "DEMONSTRATIVO":
                        statement,

                    "REGISTROS":
                        0,

                    "EMPRESAS":
                        0,

                    "ANO_MIN":
                        None,

                    "ANO_MAX":
                        None,

                    "STATUS":
                        "AUSENTE",
                }
            )

            continue

        years = pd.to_numeric(
            df["ANO"],
            errors="coerce",
        ).dropna()

        rows.append(
            {
                "DATASET":
                    dataset,

                "DEMONSTRATIVO":
                    statement,

                "REGISTROS":
                    len(df),

                "EMPRESAS":
                    df[
                        "CD_CVM"
                    ].dropna().nunique(),

                "ANO_MIN":
                    int(years.min()),

                "ANO_MAX":
                    int(years.max()),

                "STATUS":
                    "OK",
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# 14. AUDITORIA DO BENCHMARK CONGELADO
# ============================================================

def audit_frozen_loader() -> None:

    """
    Confirma que os ZIPs DFP históricos
    2019–2025 podem ser carregados usando
    a mesma arquitetura do estudo.

    Não testa scores nem ranking.
    """

    expected_years = list(
        range(2019, 2026)
    )

    available = (
        discover_available_years(
            DFP_DIR,
            "DFP",
        )
    )

    missing = [
        year
        for year in expected_years
        if year not in available
    ]

    if missing:

        raise CVMStatementLoaderError(
            "Benchmark DFP incompleto. "
            "Anos ausentes: "
            + ", ".join(
                map(str, missing)
            )
        )

    statements = (
        load_dfp_history(
            expected_years
        )
    )

    for statement in [
        "BPA",
        "BPP",
        "DRE",
    ]:

        if statements[
            statement
        ].empty:

            raise (
                CVMStatementLoaderError(
                    "Benchmark sem "
                    f"{statement}."
                )
            )


# ============================================================
# 15. RESUMO DA BASE LOCAL
# ============================================================

def local_inventory() -> dict:

    return {
        "DFP_YEARS":
            discover_available_years(
                DFP_DIR,
                "DFP",
            ),

        "ITR_YEARS":
            discover_available_years(
                ITR_DIR,
                "ITR",
            ),
    }


# ============================================================
# 16. SELF TEST
# ============================================================

def _self_test():

    assert (
        STATEMENT_MARKERS["BPA"]
        ==
        "BPA_con"
    )

    assert (
        STATEMENT_MARKERS["BPP"]
        ==
        "BPP_con"
    )

    assert (
        STATEMENT_MARKERS["DRE"]
        ==
        "DRE_con"
    )

    assert (
        STATEMENT_MARKERS["DFC_MD"]
        ==
        "DFC_MD_con"
    )

    assert (
        STATEMENT_MARKERS["DFC_MI"]
        ==
        "DFC_MI_con"
    )

    print(
        "cvm_statement_loader_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":

    _self_test()

    print(
        "Inventário CVM:",
        local_inventory(),
    )
