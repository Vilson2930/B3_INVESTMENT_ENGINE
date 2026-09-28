"""
B3 INVESTMENT ENGINE
LIVE FCA ENGINE V1

Objetivo
--------
Transformar os arquivos FCA oficiais atualizados pela camada
update_cvm_data.py na estrutura necessária ao Sector Engine V1.

Metodologia
-----------
Preserva a lógica documental da Cell8 original:

1. FCA principal -> ponte CNPJ / CD_CVM
2. somente CNPJ associado a um único CD_CVM entra na ponte segura
3. transporte de CD_CVM para FCA Geral e Valor Mobiliário
4. registro Geral mais recente por companhia
5. preservação do histórico de setor/atividade
6. preservação do histórico de tickers
7. remoção somente de duplicidade documental exata
8. nenhum ticker histórico é descartado por ser antigo
9. nenhuma empresa do universo DFP é eliminada
10. identidade oficial continua sendo CD_CVM

IMPORTANTE
----------
Este módulo:
- NÃO calcula Quality Score
- NÃO calcula Valuation
- NÃO calcula ranking
- NÃO aplica filtro de 10 anos
- NÃO aplica filtro de liquidez
- NÃO altera Sector Engine V1
- NÃO altera Quality Engine V1
- NÃO altera Valuation Engine V1
- NÃO altera Technical Engine
"""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import re
import unicodedata

import numpy as np
import pandas as pd


# ============================================================
# CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

LIVE_CVM_DIR = (
    PROJECT_ROOT
    / "data"
    / "live"
    / "cvm"
)

FCA_DIR = (
    LIVE_CVM_DIR
    / "fca"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "live"
    / "processed"
)

OUTPUT_BRIDGE = (
    OUTPUT_DIR
    / "fca_cnpj_cd_cvm_bridge.csv"
)

OUTPUT_SECTOR_HISTORY = (
    OUTPUT_DIR
    / "fca_sector_history.csv"
)

OUTPUT_SECURITY_HISTORY = (
    OUTPUT_DIR
    / "fca_security_history.csv"
)

OUTPUT_COMPANY_MASTER = (
    OUTPUT_DIR
    / "fca_company_master.csv"
)

OUTPUT_AMBIGUOUS_CNPJ = (
    OUTPUT_DIR
    / "fca_ambiguous_cnpj.csv"
)

OUTPUT_AMBIGUOUS_TICKERS = (
    OUTPUT_DIR
    / "fca_ambiguous_tickers.csv"
)


# ============================================================
# EXCEÇÃO
# ============================================================

class LiveFCAError(RuntimeError):
    """Erro estrutural na camada FCA live."""


# ============================================================
# HELPERS
# ============================================================

def normalizar_cnpj(valor) -> str | None:
    """
    Normaliza CNPJ removendo qualquer caractere não numérico.
    """

    if pd.isna(valor):
        return None

    texto = re.sub(
        r"\D",
        "",
        str(valor),
    )

    if not texto:
        return None

    return texto.zfill(14)


def limpar_texto(valor):
    """
    Limpeza conservadora de texto.
    Não cria classificação setorial.
    """

    if pd.isna(valor):
        return np.nan

    texto = str(valor).strip()

    if not texto:
        return np.nan

    return texto


def converter_data(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(
        serie,
        errors="coerce",
    )


def converter_numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie,
        errors="coerce",
    )


def limpar_ticker(valor):
    """
    Limpeza documental do código de negociação.
    Não escolhe ticker principal.
    """

    if pd.isna(valor):
        return np.nan

    ticker = str(valor).strip().upper()

    if not ticker:
        return np.nan

    if ticker in {
        "NAN",
        "NONE",
        "NULL",
    }:
        return np.nan

    return ticker


# ============================================================
# INVENTÁRIO FCA
# ============================================================

def discover_fca_files(
    fca_dir: Path | str = FCA_DIR,
) -> list[Path]:

    fca_dir = Path(fca_dir)

    if not fca_dir.exists():
        raise LiveFCAError(
            f"Pasta FCA não encontrada: {fca_dir}"
        )

    arquivos = sorted(
        fca_dir.glob(
            "fca_cia_aberta_*.zip"
        )
    )

    arquivos = [
        arquivo
        for arquivo in arquivos
        if re.fullmatch(
            r"fca_cia_aberta_\d{4}\.zip",
            arquivo.name,
        )
    ]

    if not arquivos:
        raise LiveFCAError(
            f"Nenhum ZIP FCA encontrado em {fca_dir}"
        )

    return arquivos


def extract_year(path: Path) -> int:

    match = re.search(
        r"(\d{4})",
        path.stem,
    )

    if match is None:
        raise LiveFCAError(
            f"Ano não identificado em {path.name}"
        )

    return int(
        match.group(1)
    )


# ============================================================
# LEITURA DOS CSVs INTERNOS
# ============================================================

def _find_member(
    members: list[str],
    expected_name: str,
) -> str:

    matches = [
        member
        for member in members
        if Path(member).name.lower()
        == expected_name.lower()
    ]

    if len(matches) != 1:
        raise LiveFCAError(
            "Arquivo interno FCA não localizado "
            f"de forma única: {expected_name}. "
            f"Ocorrências={len(matches)}"
        )

    return matches[0]


def _read_member(
    zip_path: Path,
    member: str,
) -> pd.DataFrame:

    with ZipFile(zip_path) as zf:

        raw = zf.read(member)

    # Arquivos oficiais FCA são normalmente latin-1.
    # O fallback evita falha meramente de encoding.
    try:

        return pd.read_csv(
            BytesIO(raw),
            sep=";",
            encoding="latin-1",
            low_memory=False,
        )

    except UnicodeDecodeError:

        return pd.read_csv(
            BytesIO(raw),
            sep=";",
            encoding="utf-8-sig",
            low_memory=False,
        )


def load_one_fca_zip(
    zip_path: Path,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:

    year = extract_year(
        zip_path
    )

    with ZipFile(zip_path) as zf:
        members = zf.namelist()

    principal_name = (
        f"fca_cia_aberta_{year}.csv"
    )

    geral_name = (
        f"fca_cia_aberta_geral_{year}.csv"
    )

    valores_name = (
        f"fca_cia_aberta_valor_mobiliario_{year}.csv"
    )

    principal_member = _find_member(
        members,
        principal_name,
    )

    geral_member = _find_member(
        members,
        geral_name,
    )

    valores_member = _find_member(
        members,
        valores_name,
    )

    principal = _read_member(
        zip_path,
        principal_member,
    )

    geral = _read_member(
        zip_path,
        geral_member,
    )

    valores = _read_member(
        zip_path,
        valores_member,
    )

    principal["ANO_FCA"] = year
    geral["ANO_FCA"] = year
    valores["ANO_FCA"] = year

    return (
        principal,
        geral,
        valores,
    )


# ============================================================
# CARREGAMENTO HISTÓRICO
# ============================================================

def load_fca_history(
    fca_dir: Path | str = FCA_DIR,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:

    arquivos = discover_fca_files(
        fca_dir
    )

    principais = []
    gerais = []
    valores = []

    for arquivo in arquivos:

        principal, geral, valor = (
            load_one_fca_zip(
                arquivo
            )
        )

        principais.append(
            principal
        )

        gerais.append(
            geral
        )

        valores.append(
            valor
        )

    return (
        pd.concat(
            principais,
            ignore_index=True,
            sort=False,
        ),
        pd.concat(
            gerais,
            ignore_index=True,
            sort=False,
        ),
        pd.concat(
            valores,
            ignore_index=True,
            sort=False,
        ),
    )


# ============================================================
# NORMALIZAÇÃO DE COLUNAS
# ============================================================

def _find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
) -> str | None:

    lookup = {
        str(col).strip().upper():
            col
        for col in df.columns
    }

    for candidate in candidates:

        key = candidate.strip().upper()

        if key in lookup:
            return lookup[key]

    if required:
        raise LiveFCAError(
            "Nenhuma das colunas esperadas foi encontrada: "
            + ", ".join(candidates)
        )

    return None


def prepare_principal(
    df: pd.DataFrame,
) -> pd.DataFrame:

    out = df.copy()

    cnpj_col = _find_column(
        out,
        [
            "CNPJ_Companhia",
            "CNPJ_CIA",
        ],
    )

    cd_col = _find_column(
        out,
        [
            "Codigo_CVM",
            "CD_CVM",
        ],
    )

    out["CNPJ_NORM"] = (
        out[cnpj_col]
        .map(normalizar_cnpj)
    )

    out["CD_CVM"] = pd.to_numeric(
        out[cd_col],
        errors="coerce",
    )

    out = (
        out
        .dropna(
            subset=[
                "CNPJ_NORM",
                "CD_CVM",
            ]
        )
        .copy()
    )

    out["CD_CVM"] = (
        out["CD_CVM"]
        .astype("int64")
    )

    return out


def prepare_geral(
    df: pd.DataFrame,
) -> pd.DataFrame:

    out = df.copy()

    cnpj_col = _find_column(
        out,
        [
            "CNPJ_Companhia",
            "CNPJ_CIA",
        ],
    )

    out["CNPJ_NORM"] = (
        out[cnpj_col]
        .map(normalizar_cnpj)
    )

    for coluna in [
        "Data_Referencia",
        "Data_Entrega",
    ]:
        if coluna in out.columns:
            out[coluna] = converter_data(
                out[coluna]
            )

    if "Versao" in out.columns:
        out["Versao"] = converter_numero(
            out["Versao"]
        )

    if "ID_Documento" in out.columns:
        out["ID_Documento"] = converter_numero(
            out["ID_Documento"]
        )

    return out


def prepare_valores(
    df: pd.DataFrame,
) -> pd.DataFrame:

    out = df.copy()

    cnpj_col = _find_column(
        out,
        [
            "CNPJ_Companhia",
            "CNPJ_CIA",
        ],
    )

    out["CNPJ_NORM"] = (
        out[cnpj_col]
        .map(normalizar_cnpj)
    )

    campos_data = [
        "Data_Referencia",
        "Data_Entrega",
        "Data_Inicio_Negociacao",
        "Data_Fim_Negociacao",
        "Data_Inicio_Listagem",
        "Data_Fim_Listagem",
    ]

    for coluna in campos_data:

        if coluna in out.columns:

            out[coluna] = converter_data(
                out[coluna]
            )

    if "Versao" in out.columns:
        out["Versao"] = converter_numero(
            out["Versao"]
        )

    if "ID_Documento" in out.columns:
        out["ID_Documento"] = converter_numero(
            out["ID_Documento"]
        )

    ticker_col = _find_column(
        out,
        [
            "Codigo_Negociacao",
            "Código_Negociação",
        ],
        required=False,
    )

    if ticker_col is None:
        raise LiveFCAError(
            "FCA Valor Mobiliário sem Codigo_Negociacao."
        )

    out["TICKER"] = (
        out[ticker_col]
        .map(limpar_ticker)
    )

    return out


# ============================================================
# PONTE CNPJ -> CD_CVM
# ============================================================

def build_safe_bridge(
    principal: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:

    pares = (
        principal[
            [
                "CNPJ_NORM",
                "CD_CVM",
            ]
        ]
        .dropna()
        .drop_duplicates()
    )

    contagem = (
        pares
        .groupby("CNPJ_NORM")[
            "CD_CVM"
        ]
        .nunique()
        .reset_index(
            name="QTD_CD_CVM"
        )
    )

    ambiguos = (
        contagem[
            contagem[
                "QTD_CD_CVM"
            ] > 1
        ]
        .merge(
            pares,
            on="CNPJ_NORM",
            how="left",
        )
        .sort_values(
            [
                "CNPJ_NORM",
                "CD_CVM",
            ]
        )
        .reset_index(drop=True)
    )

    cnpjs_seguros = set(
        contagem.loc[
            contagem[
                "QTD_CD_CVM"
            ].eq(1),
            "CNPJ_NORM",
        ]
    )

    ponte_segura = (
        pares[
            pares[
                "CNPJ_NORM"
            ].isin(
                cnpjs_seguros
            )
        ]
        .drop_duplicates(
            subset=["CNPJ_NORM"]
        )
        .copy()
    )

    if (
        ponte_segura[
            "CNPJ_NORM"
        ]
        .duplicated()
        .any()
    ):
        raise LiveFCAError(
            "Ponte segura contém CNPJ duplicado."
        )

    return (
        ponte_segura,
        ambiguos,
    )


# ============================================================
# TRANSPORTAR CD_CVM
# ============================================================

def attach_cd_cvm(
    df: pd.DataFrame,
    ponte_segura: pd.DataFrame,
) -> pd.DataFrame:

    out = (
        df
        .merge(
            ponte_segura[
                [
                    "CNPJ_NORM",
                    "CD_CVM",
                ]
            ],
            on="CNPJ_NORM",
            how="left",
            validate="many_to_one",
        )
    )

    return out


# ============================================================
# FCA GERAL — REGISTRO ATUAL
# ============================================================

def build_sector_history(
    geral: pd.DataFrame,
) -> pd.DataFrame:

    colunas = [
        coluna
        for coluna in [
            "CD_CVM",
            "CNPJ_NORM",
            "Data_Referencia",
            "Versao",
            "ID_Documento",
            "ANO_FCA",
            "Nome_Empresarial",
            "Situacao_Registro_CVM",
            "Setor_Atividade",
            "Descricao_Atividade",
            "Situacao_Emissor",
        ]
        if coluna in geral.columns
    ]

    historico = (
        geral[
            colunas
        ]
        .dropna(
            subset=["CD_CVM"]
        )
        .copy()
    )

    historico["CD_CVM"] = (
        pd.to_numeric(
            historico["CD_CVM"],
            errors="coerce",
        )
    )

    historico = (
        historico
        .dropna(
            subset=["CD_CVM"]
        )
    )

    historico["CD_CVM"] = (
        historico["CD_CVM"]
        .astype("int64")
    )

    return historico


def build_latest_general(
    geral: pd.DataFrame,
) -> pd.DataFrame:

    base = (
        build_sector_history(
            geral
        )
    )

    sort_cols = [
        coluna
        for coluna in [
            "CD_CVM",
            "Data_Referencia",
            "Versao",
            "ID_Documento",
            "ANO_FCA",
        ]
        if coluna in base.columns
    ]

    if "Data_Referencia" not in base.columns:
        raise LiveFCAError(
            "FCA Geral sem Data_Referencia."
        )

    # Cell8:
    # primeiro conserva a última versão documental
    # por companhia/data de referência.
    dedup_cols = [
        "CD_CVM",
        "Data_Referencia",
    ]

    base = (
        base
        .sort_values(
            sort_cols,
            na_position="first",
        )
        .drop_duplicates(
            subset=dedup_cols,
            keep="last",
        )
    )

    # Depois seleciona o registro mais recente da companhia.
    latest = (
        base
        .sort_values(
            sort_cols,
            na_position="first",
        )
        .drop_duplicates(
            subset=["CD_CVM"],
            keep="last",
        )
        .copy()
    )

    rename = {}

    if "Setor_Atividade" in latest.columns:
        rename[
            "Setor_Atividade"
        ] = "FCA_SETOR_ATIVIDADE"

    if "Descricao_Atividade" in latest.columns:
        rename[
            "Descricao_Atividade"
        ] = "FCA_DESCRICAO_ATIVIDADE"

    if "Nome_Empresarial" in latest.columns:
        rename[
            "Nome_Empresarial"
        ] = "FCA_NOME_EMPRESARIAL"

    if "Situacao_Registro_CVM" in latest.columns:
        rename[
            "Situacao_Registro_CVM"
        ] = "FCA_SITUACAO_REGISTRO"

    if "Situacao_Emissor" in latest.columns:
        rename[
            "Situacao_Emissor"
        ] = "FCA_SITUACAO_EMISSOR"

    latest = latest.rename(
        columns=rename
    )

    return latest


# ============================================================
# VALORES MOBILIÁRIOS / TICKERS
# ============================================================

def build_security_history(
    valores: pd.DataFrame,
) -> pd.DataFrame:

    base = valores.copy()

    base["CD_CVM"] = pd.to_numeric(
        base["CD_CVM"],
        errors="coerce",
    )

    base = (
        base
        .dropna(
            subset=["CD_CVM"]
        )
        .copy()
    )

    base["CD_CVM"] = (
        base["CD_CVM"]
        .astype("int64")
    )

    # Cell8 não escolhe um ticker principal nesta fase.
    # Ticker antigo continua fazendo parte do histórico.

    document_keys = [
        coluna
        for coluna in [
            "CD_CVM",
            "Data_Referencia",
            "Versao",
            "ID_Documento",
            "Valor_Mobiliario",
            "TICKER",
            "Mercado",
            "Entidade_Administradora",
            "Data_Inicio_Negociacao",
            "Data_Fim_Negociacao",
            "Segmento",
            "ANO_FCA",
        ]
        if coluna in base.columns
    ]

    if document_keys:

        base = (
            base
            .drop_duplicates(
                subset=document_keys
            )
            .copy()
        )

    return base


def audit_ambiguous_tickers(
    security_history: pd.DataFrame,
) -> pd.DataFrame:

    base = (
        security_history[
            [
                "CD_CVM",
                "TICKER",
            ]
        ]
        .dropna(
            subset=["TICKER"]
        )
        .drop_duplicates()
    )

    contagem = (
        base
        .groupby("TICKER")[
            "CD_CVM"
        ]
        .nunique()
        .reset_index(
            name="QTD_CD_CVM"
        )
    )

    ambiguos = (
        contagem[
            contagem[
                "QTD_CD_CVM"
            ] > 1
        ]
        .merge(
            base,
            on="TICKER",
            how="left",
        )
        .sort_values(
            [
                "TICKER",
                "CD_CVM",
            ]
        )
        .reset_index(drop=True)
    )

    return ambiguos


def build_ticker_summary(
    security_history: pd.DataFrame,
) -> pd.DataFrame:

    base = (
        security_history[
            [
                "CD_CVM",
                "TICKER",
            ]
        ]
        .dropna(
            subset=["TICKER"]
        )
        .drop_duplicates()
    )

    resumo = (
        base
        .groupby("CD_CVM")[
            "TICKER"
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
            name="FCA_TICKERS_HISTORICOS"
        )
    )

    return resumo


# ============================================================
# MASTER FCA
# ============================================================

def build_fca_master(
    latest_general: pd.DataFrame,
    ticker_summary: pd.DataFrame,
) -> pd.DataFrame:

    master = (
        latest_general
        .merge(
            ticker_summary,
            on="CD_CVM",
            how="left",
            validate="one_to_one",
        )
    )

    return master


# ============================================================
# CRUZAMENTO COM UNIVERSO DFP
# ============================================================

def cross_with_identity(
    identity: pd.DataFrame,
    fca_master: pd.DataFrame,
) -> pd.DataFrame:

    required = {
        "CD_CVM",
        "DENOM_CIA_ATUAL",
    }

    missing = sorted(
        required.difference(
            identity.columns
        )
    )

    if missing:
        raise LiveFCAError(
            "Identidade CVM sem campos obrigatórios: "
            + ", ".join(missing)
        )

    universo = (
        identity[
            [
                "CD_CVM",
                "DENOM_CIA_ATUAL",
            ]
        ]
        .copy()
    )

    universo["CD_CVM"] = pd.to_numeric(
        universo["CD_CVM"],
        errors="coerce",
    )

    universo = (
        universo
        .dropna(
            subset=["CD_CVM"]
        )
    )

    universo["CD_CVM"] = (
        universo["CD_CVM"]
        .astype("int64")
    )

    if universo["CD_CVM"].duplicated().any():
        raise LiveFCAError(
            "Universo DFP possui CD_CVM duplicado."
        )

    resultado = (
        universo
        .merge(
            fca_master,
            on="CD_CVM",
            how="left",
            indicator="_MERGE_FCA",
            validate="one_to_one",
        )
    )

    resultado[
        "FCA_LOCALIZADO"
    ] = (
        resultado[
            "_MERGE_FCA"
        ].eq("both")
    )

    resultado = (
        resultado
        .drop(
            columns=[
                "_MERGE_FCA"
            ]
        )
    )

    # Nenhuma empresa do universo DFP pode desaparecer.
    if len(resultado) != len(universo):
        raise LiveFCAError(
            "Quantidade de empresas mudou no cruzamento FCA."
        )

    if (
        set(resultado["CD_CVM"])
        !=
        set(universo["CD_CVM"])
    ):
        raise LiveFCAError(
            "Universo CD_CVM foi alterado pelo FCA."
        )

    return resultado


# ============================================================
# AUDITORIA FINAL
# ============================================================

def audit_final_master(
    master: pd.DataFrame,
) -> dict:

    total = len(master)

    unique = (
        master[
            "CD_CVM"
        ]
        .nunique()
    )

    duplicated = int(
        master[
            "CD_CVM"
        ]
        .duplicated()
        .sum()
    )

    if duplicated != 0:
        raise LiveFCAError(
            "Master FCA contém CD_CVM duplicado."
        )

    if total != unique:
        raise LiveFCAError(
            "Master FCA não possui relação 1:1 por CD_CVM."
        )

    localized = int(
        master[
            "FCA_LOCALIZADO"
        ].sum()
    )

    return {
        "companies": total,
        "unique_cd_cvm": unique,
        "duplicate_cd_cvm": duplicated,
        "fca_found": localized,
        "fca_missing": total - localized,
        "status": "VALIDATED",
    }


# ============================================================
# ENGINE PRINCIPAL
# ============================================================

def run_live_fca_engine(
    identity: pd.DataFrame,
    fca_dir: Path | str = FCA_DIR,
    save_outputs: bool = True,
) -> pd.DataFrame:
    """
    Executa a camada FCA live.

    Entrada
    -------
    identity:
        Saída do live_identity_engine.py.

    Saída
    -----
    DataFrame compatível com a entrada empresarial
    necessária ao sector_engine_v1.py.
    """

    print("=" * 72)
    print("LIVE FCA ENGINE V1")
    print("=" * 72)

    # --------------------------------------------------------
    # 1. CARREGAR FCA
    # --------------------------------------------------------

    principal, geral, valores = (
        load_fca_history(
            fca_dir
        )
    )

    # --------------------------------------------------------
    # 2. NORMALIZAR
    # --------------------------------------------------------

    principal = prepare_principal(
        principal
    )

    geral = prepare_geral(
        geral
    )

    valores = prepare_valores(
        valores
    )

    # --------------------------------------------------------
    # 3. PONTE SEGURA
    # --------------------------------------------------------

    ponte_segura, ambiguos_cnpj = (
        build_safe_bridge(
            principal
        )
    )

    # --------------------------------------------------------
    # 4. TRANSPORTAR CD_CVM
    # --------------------------------------------------------

    geral = attach_cd_cvm(
        geral,
        ponte_segura,
    )

    valores = attach_cd_cvm(
        valores,
        ponte_segura,
    )

    # --------------------------------------------------------
    # 5. FCA GERAL
    # --------------------------------------------------------

    sector_history = (
        build_sector_history(
            geral
        )
    )

    latest_general = (
        build_latest_general(
            geral
        )
    )

    # --------------------------------------------------------
    # 6. VALORES MOBILIÁRIOS
    # --------------------------------------------------------

    security_history = (
        build_security_history(
            valores
        )
    )

    ambiguous_tickers = (
        audit_ambiguous_tickers(
            security_history
        )
    )

    ticker_summary = (
        build_ticker_summary(
            security_history
        )
    )

    # --------------------------------------------------------
    # 7. MASTER FCA
    # --------------------------------------------------------

    fca_master = (
        build_fca_master(
            latest_general,
            ticker_summary,
        )
    )

    # --------------------------------------------------------
    # 8. CRUZAR COM UNIVERSO DFP
    # --------------------------------------------------------

    final_master = (
        cross_with_identity(
            identity,
            fca_master,
        )
    )

    # --------------------------------------------------------
    # 9. AUDITORIA
    # --------------------------------------------------------

    audit = (
        audit_final_master(
            final_master
        )
    )

    # --------------------------------------------------------
    # 10. SALVAR
    # --------------------------------------------------------

    if save_outputs:

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        ponte_segura.to_csv(
            OUTPUT_BRIDGE,
            index=False,
            encoding="utf-8-sig",
        )

        sector_history.to_csv(
            OUTPUT_SECTOR_HISTORY,
            index=False,
            encoding="utf-8-sig",
        )

        security_history.to_csv(
            OUTPUT_SECURITY_HISTORY,
            index=False,
            encoding="utf-8-sig",
        )

        final_master.to_csv(
            OUTPUT_COMPANY_MASTER,
            index=False,
            encoding="utf-8-sig",
        )

        ambiguos_cnpj.to_csv(
            OUTPUT_AMBIGUOUS_CNPJ,
            index=False,
            encoding="utf-8-sig",
        )

        ambiguous_tickers.to_csv(
            OUTPUT_AMBIGUOUS_TICKERS,
            index=False,
            encoding="utf-8-sig",
        )

    # --------------------------------------------------------
    # 11. RESULTADO
    # --------------------------------------------------------

    arquivos = discover_fca_files(
        fca_dir
    )

    anos = [
        extract_year(
            arquivo
        )
        for arquivo in arquivos
    ]

    print(
        "FCA:",
        f"{min(anos)}–{max(anos)}",
    )

    print(
        "Arquivos FCA:",
        len(arquivos),
    )

    print(
        "Companhias no universo DFP:",
        audit["companies"],
    )

    print(
        "CD_CVM únicos:",
        audit["unique_cd_cvm"],
    )

    print(
        "FCA localizado:",
        audit["fca_found"],
    )

    print(
        "FCA não localizado:",
        audit["fca_missing"],
    )

    print(
        "CNPJ ambíguos:",
        ambiguos_cnpj[
            "CNPJ_NORM"
        ].nunique()
        if len(ambiguos_cnpj)
        else 0,
    )

    print(
        "Tickers ligados a >1 CD_CVM:",
        ambiguous_tickers[
            "TICKER"
        ].nunique()
        if len(ambiguous_tickers)
        else 0,
    )

    print()
    print("Empresa eliminada pelo FCA: NÃO")
    print("Filtro de 10 anos aplicado: NÃO")
    print("Filtro de liquidez aplicado: NÃO")
    print("Quality Score calculado: NÃO")
    print("Valuation calculado: NÃO")
    print("Ranking calculado: NÃO")
    print("Identidade oficial: CD_CVM")
    print()
    print("Sector Engine alterado: NÃO")
    print("Quality Engine alterado: NÃO")
    print("Valuation Engine alterado: NÃO")
    print("Technical Engine alterado: NÃO")
    print("=" * 72)
    print("✓ LIVE FCA ENGINE CONCLUÍDO")
    print("=" * 72)

    return final_master


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "LiveFCAError",
    "normalizar_cnpj",
    "limpar_texto",
    "converter_data",
    "converter_numero",
    "limpar_ticker",
    "discover_fca_files",
    "load_one_fca_zip",
    "load_fca_history",
    "prepare_principal",
    "prepare_geral",
    "prepare_valores",
    "build_safe_bridge",
    "attach_cd_cvm",
    "build_sector_history",
    "build_latest_general",
    "build_security_history",
    "audit_ambiguous_tickers",
    "build_ticker_summary",
    "build_fca_master",
    "cross_with_identity",
    "audit_final_master",
    "run_live_fca_engine",
]
