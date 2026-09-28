"""
B3 INVESTMENT ENGINE
SECTOR ENGINE V1

Reprodução da arquitetura setorial validada no estudo original.

Origem metodológica:
- Cell 09: classificação preliminar
- Cell 10: auditoria econômica
- Cell 11: resolução determinística
- Cell 12: correção AEGEA + congelamento

IMPORTANTE
----------
Este módulo NÃO:
- calcula Quality Score;
- calcula Valuation;
- aplica liquidez;
- aplica histórico mínimo;
- elimina empresa por desempenho;
- altera metodologia automaticamente.

Casos sem evidência suficiente permanecem AUDITAR.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd


# ============================================================
# 1. MOTORES V1
# ============================================================

VALID_ENGINES = {
    "FINANCEIRO_BANCO",
    "FINANCEIRO_SEGUROS",
    "FINANCEIRO_ESPECIAL",
    "UTILITY",
    "COMMODITY",
    "OPERACIONAL",
    "IMOBILIARIO",
    "AMBIENTAL_RESIDUOS",
    "AUDITAR",
}


# ============================================================
# 2. NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto) -> str:

    if pd.isna(texto):
        return ""

    texto = str(texto).upper().strip()

    texto = "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFKD",
            texto,
        )
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto


# ============================================================
# 3. SETORES EXPLÍCITOS — CELL 09
# ============================================================

SETORES_BANCOS = {
    "BANCOS",
    "EMP. ADM. PART. - BANCOS",
    "INTERMEDIACAO FINANCEIRA",
    "EMP. ADM. PART. - INTERMEDIACAO FINANCEIRA",
}

SETORES_SEGUROS = {
    "SEGURADORAS E CORRETORAS",
    "EMP. ADM. PART. - SEGURADORAS E CORRETORAS",
}

SETORES_UTILITY = {
    "ENERGIA ELETRICA",
    "EMP. ADM. PART. - ENERGIA ELETRICA",
    "SANEAMENTO, SERV. AGUA E GAS",
    "EMP. ADM. PART. - SANEAMENTO, SERV. AGUA E GAS",
}

SETORES_COMMODITY = {
    "PETROLEO E GAS",
    "EMP. ADM. PART. - PETROLEO E GAS",
    "EXTRACAO MINERAL",
    "EMP. ADM. PART. - EXTRACAO MINERAL",
    "PAPEL E CELULOSE",
    "EMP. ADM. PART. - PAPEL E CELULOSE",
    "METALURGIA E SIDERURGIA",
    "EMP. ADM. PART. - METALURGIA E SIDERURGIA",
    "AGRICULTURA (ACUCAR, ALCOOL E CANA)",
    "EMP. ADM. PART. - AGRICULTURA (ACUCAR, ALCOOL E CANA)",
}

SETORES_AUDITAR = {
    "",
    "SECURITIZACAO DE RECEBIVEIS",
    "EMP. ADM. PART. - CREDITO IMOBILIARIO",
    "BOLSAS DE VALORES/MERCADORIAS E FUTUROS",
    "EMP. ADM. PART. - SEM SETOR PRINCIPAL",
}


# ============================================================
# 4. PADRÕES DE AUDITORIA — CELL 10
# ============================================================

PADROES = {

    "EXTRACAO_PRODUCAO_COMMODITY": [
        r"\bMINERAC",
        r"\bEXTRAC",
        r"\bLAVRA\b",
        r"\bJAZIDA",
        r"\bPETROLEO\b",
        r"\bGAS NATURAL\b",
        r"\bPRODUCAO DE CANA",
        r"\bCANA-DE-ACUCAR\b",
        r"\bACUCAR\b",
        r"\bETANOL\b",
        r"\bCELULOSE\b",
        r"\bSIDERURG",
    ],

    "INDUSTRIAL_MANUFATURA": [
        r"\bFABRICAC",
        r"\bINDUSTRIA\b",
        r"\bINDUSTRIALIZ",
        r"\bMAQUIN",
        r"\bEQUIPAMENT",
        r"\bPECAS\b",
        r"\bCOMPONENT",
        r"\bFUNDICAO\b",
        r"\bUSINAGEM\b",
    ],

    "SERVICOS": [
        r"\bPRESTACAO DE SERVICOS\b",
        r"\bSERVICOS DE\b",
        r"\bCONSULTORIA\b",
        r"\bENGENHARIA\b",
        r"\bAPOIO MARITIMO\b",
        r"\bSUPORTE MARITIMO\b",
    ],

    "ENERGIA_REGULADA": [
        r"\bCONCESSION",
        r"\bDISTRIBUICAO DE ENERGIA\b",
        r"\bTRANSMISSAO DE ENERGIA\b",
        r"\bGERACAO DE ENERGIA\b",
        r"\bGERACAO E TRANSMISSAO\b",
        r"\bSERVICO PUBLICO\b",
    ],

    "SANEAMENTO_REGULADO": [
        r"\bABASTECIMENTO DE AGUA\b",
        r"\bESGOTAMENTO SANITARIO\b",
        r"\bSERVICOS PUBLICOS DE.*AGUA\b",
        r"\bSERVICOS DE SANEAMENTO\b",
    ],

    "RESIDUOS_AMBIENTAL": [
        r"\bRESIDU",
        r"\bATERRO",
        r"\bLIMPEZA URBANA\b",
        r"\bENGENHARIA AMBIENTAL\b",
        r"\bEMERGENCIA AMBIENTAL\b",
    ],

    "IMOBILIARIO": [
        r"\bIMOVEIS\b",
        r"\bIMOBILIAR",
        r"\bINCORPORAC",
        r"\bLOCACAO DE BENS IMOVEIS\b",
        r"\bLOCACAO DE IMOVEIS\b",
        r"\bARRENDAMENTO\b",
    ],

    "MERCADO_FINANCEIRO": [
        r"\bBANCO\b",
        r"\bFINANCEIR",
        r"\bCORRETORA\b",
        r"\bTITULOS\b",
        r"\bVALORES MOBILIARIOS\b",
        r"\bCREDITO\b",
        r"\bSECURITIZ",
        r"\bSEGUROS\b",
    ],

    "HOLDING_GENERICA": [
        r"\bHOLDING\b",
        r"\bPARTICIPACAO EM OUTRAS SOCIEDADES\b",
        r"\bPARTICIPACOES EM OUTRAS SOCIEDADES\b",
        r"\bPARTICIPACAO NO CAPITAL\b",
    ],
}


def encontrou_padrao(texto: str, padroes: list[str]) -> bool:

    if not texto:
        return False

    return any(
        re.search(
            padrao,
            texto,
        ) is not None
        for padrao in padroes
    )


# ============================================================
# 5. CLASSIFICAÇÃO PRELIMINAR — CELL 09
# ============================================================

def classificar_motor_preliminar(row):

    setor = row["SETOR_NORM"]

    assinatura_fin = bool(
        row["ASSINATURA_DRE_FINANCEIRA"]
    )

    if setor in SETORES_BANCOS:

        return pd.Series(
            [
                "FINANCEIRO_BANCO",
                "FCA_SETOR_FINANCEIRO",
                "ALTA",
            ]
        )

    if assinatura_fin:

        return pd.Series(
            [
                "FINANCEIRO_BANCO",
                "DRE_INTERMEDIACAO_FINANCEIRA",
                "ALTA",
            ]
        )

    if setor in SETORES_SEGUROS:

        return pd.Series(
            [
                "FINANCEIRO_SEGUROS",
                "FCA_SETOR_SEGUROS",
                "ALTA",
            ]
        )

    if setor in SETORES_UTILITY:

        return pd.Series(
            [
                "UTILITY",
                "FCA_SETOR_UTILITY",
                "ALTA",
            ]
        )

    if setor in SETORES_COMMODITY:

        return pd.Series(
            [
                "COMMODITY",
                "FCA_SETOR_COMMODITY",
                "ALTA",
            ]
        )

    if setor in SETORES_AUDITAR:

        return pd.Series(
            [
                "AUDITAR",
                "FCA_SETOR_INSUFICIENTE_OU_ESPECIAL",
                "BAIXA",
            ]
        )

    return pd.Series(
        [
            "OPERACIONAL",
            "FCA_SETOR_OPERACIONAL",
            "ALTA",
        ]
    )


# ============================================================
# 6. CELL 11 — CORREÇÕES DETERMINÍSTICAS RECUPERADAS
# ============================================================

COMMODITY_PARA_OPERACIONAL = {

    27430: "FABRICACAO_CABOS_NAO_COMMODITY",
    1562: "EQUIPAMENTOS_MEDICO_HOSPITALARES",
    23620: "SERVICOS_APOIO_MARITIMO_OLEO_GAS",
    3069: "FABRICACAO_FERROLIGAS",
    5380: "FUNDICAO_INDUSTRIAL",
    13366: "FABRICACAO_FECHADURAS",
    7870: "MAQUINAS_E_EQUIPAMENTOS_AGROINDUSTRIA",
    8753: "MAQUINAS_E_EQUIPAMENTOS_AGRICOLAS",
    9040: "FABRICACAO_ARTIGOS_DE_VIDRO",
    21334: "FABRICACAO_FERTILIZANTES",
    26956: "SERVICOS_ENGENHARIA_SUBMARINA",
    94: "INDUSTRIALIZACAO_ACOS_PLANOS",
    14664: "INDUSTRIA_METALURGICA",
    11991: "FABRICACAO_COMPONENTES_AUTOMOTIVOS_E_ELETRICOS",
}

COMMODITY_CICLICA_COMPLEXA = {
    20354,
    25950,
}

AMBIENTAL_RESIDUOS = {
    23396,
    24961,
    26271,
    27049,
    25550,
    27073,
}

FINANCEIRO_ESPECIAL = {
    21610: "INFRAESTRUTURA_MERCADO_CAPITAIS",
    18287: "SECURITIZADORA",
    20818: "SECURITIZADORA",
    17922: "ARQUITETURA_DRE_FINANCEIRA",
    80217: "ARQUITETURA_DRE_FINANCEIRA",
    27111: "ARQUITETURA_DRE_FINANCEIRA",
}

IMOBILIARIAS = {
    19925,
    26689,
    13781,
}

OPERACIONAIS_RESOLVIDOS = {
    15458: "INDUSTRIALIZACAO_MADEIRAS_TRADING",
    20044: "PROCESSAMENTO_PAGAMENTOS_SERVICOS_DIGITAIS",
}


# ============================================================
# 7. SUBTIPOS V1
# ============================================================

SUBTIPOS = {
    "FINANCEIRO_BANCO": "BANCO_OU_INTERMEDIACAO",
    "FINANCEIRO_SEGUROS": "SEGUROS",
    "FINANCEIRO_ESPECIAL": "FINANCEIRO_NAO_BANCARIO",
    "UTILITY": "CONCESSAO_INFRAESTRUTURA",
    "AMBIENTAL_RESIDUOS": "RESIDUOS_SERVICOS_AMBIENTAIS",
    "COMMODITY": "CICLICO_COMMODITY",
    "IMOBILIARIO": "IMOBILIARIO",
    "OPERACIONAL": "OPERACIONAL_NAO_FINANCEIRO",
    "AUDITAR": "PENDENTE",
}


# ============================================================
# 8. ALTERAÇÃO SEGURA
# ============================================================

def alterar_motor(
    df: pd.DataFrame,
    cd_cvm: int,
    novo_motor: str,
    regra: str,
    confianca: str = "ALTA",
) -> None:

    mask = df["CD_CVM"].eq(cd_cvm)

    if int(mask.sum()) != 1:
        return

    df.loc[
        mask,
        "MOTOR_FINAL",
    ] = novo_motor

    df.loc[
        mask,
        "REGRA_RESOLUCAO",
    ] = regra

    df.loc[
        mask,
        "STATUS_RESOLUCAO",
    ] = "RESOLVIDO"

    df.loc[
        mask,
        "CONFIANCA_FINAL",
    ] = confianca


# ============================================================
# 9. ENGINE
# ============================================================

def run_sector_engine(
    companies: pd.DataFrame,
    dre: pd.DataFrame,
) -> pd.DataFrame:

    required_companies = {
        "CD_CVM",
        "DENOM_CIA_ATUAL",
        "FCA_LOCALIZADO",
        "FCA_SETOR_ATIVIDADE",
        "FCA_DESCRICAO_ATIVIDADE",
    }

    missing = (
        required_companies
        - set(companies.columns)
    )

    if missing:

        raise ValueError(
            "Sector Engine sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    required_dre = {
        "CD_CVM",
        "DS_CONTA",
    }

    missing_dre = (
        required_dre
        - set(dre.columns)
    )

    if missing_dre:

        raise ValueError(
            "DRE sem colunas obrigatórias: "
            + ", ".join(sorted(missing_dre))
        )

    df = companies.copy()

    if df["CD_CVM"].duplicated().any():

        raise ValueError(
            "CD_CVM duplicado no Sector Engine."
        )

    df["SETOR_NORM"] = (
        df["FCA_SETOR_ATIVIDADE"]
        .map(normalizar_texto)
    )

    df["ATIVIDADE_NORM"] = (
        df["FCA_DESCRICAO_ATIVIDADE"]
        .map(normalizar_texto)
    )

    df["NOME_NORM"] = (
        df["DENOM_CIA_ATUAL"]
        .map(normalizar_texto)
    )

    # ========================================================
    # ASSINATURA DRE FINANCEIRA
    # ========================================================

    dre_aux = dre[
        [
            "CD_CVM",
            "DS_CONTA",
        ]
    ].copy()

    dre_aux["DS_CONTA_NORM"] = (
        dre_aux["DS_CONTA"]
        .map(normalizar_texto)
    )

    assinatura = set(
        pd.to_numeric(
            dre_aux.loc[
                dre_aux[
                    "DS_CONTA_NORM"
                ].str.contains(
                    "INTERMEDIACAO FINANCEIRA",
                    na=False,
                ),
                "CD_CVM",
            ],
            errors="coerce",
        )
        .dropna()
        .astype(int)
        .unique()
    )

    df[
        "ASSINATURA_DRE_FINANCEIRA"
    ] = (
        df["CD_CVM"]
        .isin(assinatura)
    )

    # ========================================================
    # CLASSIFICAÇÃO PRELIMINAR
    # ========================================================

    df[
        [
            "MOTOR_PRELIMINAR",
            "MOTIVO_MOTOR",
            "CONFIANCA_MOTOR",
        ]
    ] = df.apply(
        classificar_motor_preliminar,
        axis=1,
    )

    # ========================================================
    # CONFLITO FCA x DRE
    # ========================================================

    df["CONFLITO_FCA_DRE"] = (
        df[
            "ASSINATURA_DRE_FINANCEIRA"
        ]
        &
        ~df[
            "SETOR_NORM"
        ].isin(SETORES_BANCOS)
    )

    mask = df["CONFLITO_FCA_DRE"]

    df.loc[
        mask,
        "MOTOR_PRELIMINAR",
    ] = "AUDITAR"

    df.loc[
        mask,
        "MOTIVO_MOTOR",
    ] = "CONFLITO_FCA_VS_DRE"

    df.loc[
        mask,
        "CONFIANCA_MOTOR",
    ] = "BAIXA"

    # ========================================================
    # SEM FCA
    # ========================================================

    mask = ~df["FCA_LOCALIZADO"].fillna(False)

    df.loc[
        mask,
        "MOTOR_PRELIMINAR",
    ] = "AUDITAR"

    df.loc[
        mask,
        "MOTIVO_MOTOR",
    ] = "SEM_FCA"

    df.loc[
        mask,
        "CONFIANCA_MOTOR",
    ] = "BAIXA"

    # ========================================================
    # EVIDÊNCIAS CELL 10
    # ========================================================

    for evidencia, padroes in PADROES.items():

        df[
            "EV_" + evidencia
        ] = (
            df["ATIVIDADE_NORM"]
            .apply(
                lambda texto:
                encontrou_padrao(
                    texto,
                    padroes,
                )
            )
        )

    mask_commodity = (
        df["MOTOR_PRELIMINAR"]
        .eq("COMMODITY")
    )

    df["ALERTA_COMMODITY"] = (
        mask_commodity
        &
        (
            df["EV_INDUSTRIAL_MANUFATURA"]
            |
            df["EV_SERVICOS"]
        )
        &
        ~df[
            "EV_EXTRACAO_PRODUCAO_COMMODITY"
        ]
    )

    mask_utility = (
        df["MOTOR_PRELIMINAR"]
        .eq("UTILITY")
    )

    df[
        "EVIDENCIA_UTILITY_REGULADA"
    ] = (
        df["EV_ENERGIA_REGULADA"]
        |
        df["EV_SANEAMENTO_REGULADO"]
    )

    df["ALERTA_UTILITY"] = (
        mask_utility
        &
        df["EV_RESIDUOS_AMBIENTAL"]
        &
        ~df[
            "EVIDENCIA_UTILITY_REGULADA"
        ]
    )

    # ========================================================
    # HIPÓTESES CELL 10
    # ========================================================

    mask_auditar = (
        df["MOTOR_PRELIMINAR"]
        .eq("AUDITAR")
    )

    df["HIPOTESE_AUDITORIA"] = ""

    mask = (
        mask_auditar
        &
        (
            df[
                "ASSINATURA_DRE_FINANCEIRA"
            ]
            |
            df[
                "EV_MERCADO_FINANCEIRO"
            ]
        )
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "FINANCEIRO_ESPECIAL"

    mask = (
        mask_auditar
        &
        df["EV_IMOBILIARIO"]
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "IMOBILIARIO"

    mask = (
        mask_auditar
        &
        df[
            "EV_EXTRACAO_PRODUCAO_COMMODITY"
        ]
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "COMMODITY_POSSIVEL"

    mask = (
        mask_auditar
        &
        df[
            "EVIDENCIA_UTILITY_REGULADA"
        ]
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "UTILITY_POSSIVEL"

    mask = (
        mask_auditar
        &
        (
            df[
                "EV_INDUSTRIAL_MANUFATURA"
            ]
            |
            df["EV_SERVICOS"]
        )
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "OPERACIONAL_POSSIVEL"

    mask = (
        mask_auditar
        &
        df["EV_HOLDING_GENERICA"]
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "HOLDING_AUDITAR"

    mask = (
        mask_auditar
        &
        df[
            "HIPOTESE_AUDITORIA"
        ].eq("")
    )

    df.loc[
        mask,
        "HIPOTESE_AUDITORIA",
    ] = "SEM_EVIDENCIA_SUFICIENTE"

    # ========================================================
    # CELL 11
    # ========================================================

    df["MOTOR_ORIGINAL"] = (
        df["MOTOR_PRELIMINAR"]
    )

    df["MOTOR_FINAL"] = (
        df["MOTOR_PRELIMINAR"]
    )

    df["REGRA_RESOLUCAO"] = (
        "MANTIDO_CLASSIFICACAO_PRELIMINAR"
    )

    df["STATUS_RESOLUCAO"] = "RESOLVIDO"

    df["CONFIANCA_FINAL"] = (
        df["CONFIANCA_MOTOR"]
    )

    # Commodity → operacional

    for cd_cvm, motivo in (
        COMMODITY_PARA_OPERACIONAL.items()
    ):

        alterar_motor(
            df,
            cd_cvm,
            "OPERACIONAL",
            (
                "CORRECAO_COMMODITY_PARA_OPERACIONAL__"
                + motivo
            ),
        )

    # Commodity complexa

    for cd_cvm in COMMODITY_CICLICA_COMPLEXA:

        mask = df["CD_CVM"].eq(cd_cvm)

        if int(mask.sum()) == 1:

            df.loc[
                mask,
                "REGRA_RESOLUCAO",
            ] = (
                "COMMODITY_AGROINDUSTRIAL_COMPLEXA"
            )

            df.loc[
                mask,
                "CONFIANCA_FINAL",
            ] = "MEDIA"

    # Ambiental / resíduos

    for cd_cvm in AMBIENTAL_RESIDUOS:

        alterar_motor(
            df,
            cd_cvm,
            "AMBIENTAL_RESIDUOS",
            (
                "FCA_RESIDUOS_AMBIENTAL_"
                "NAO_UTILITY_REGULADA"
            ),
        )

    # Financeiro especial

    for cd_cvm, motivo in (
        FINANCEIRO_ESPECIAL.items()
    ):

        alterar_motor(
            df,
            cd_cvm,
            "FINANCEIRO_ESPECIAL",
            "FINANCEIRO_ESPECIAL__" + motivo,
        )

    # Sul 116

    mask = df["CD_CVM"].eq(16438)

    if int(mask.sum()) == 1:

        df.loc[
            mask,
            "MOTOR_FINAL",
        ] = "AUDITAR"

        df.loc[
            mask,
            "REGRA_RESOLUCAO",
        ] = (
            "CONFLITO_REAL_FCA_TELECOM_"
            "VS_DRE_FINANCEIRA"
        )

        df.loc[
            mask,
            "STATUS_RESOLUCAO",
        ] = "PENDENTE"

        df.loc[
            mask,
            "CONFIANCA_FINAL",
        ] = "BAIXA"

    # Dexxos

    mask = df["CD_CVM"].eq(16632)

    if int(mask.sum()) == 1:

        df.loc[
            mask,
            "MOTOR_FINAL",
        ] = "AUDITAR"

        df.loc[
            mask,
            "REGRA_RESOLUCAO",
        ] = (
            "FALSO_POSITIVO_TEXTO_"
            "NAO_FINANCEIRAS"
        )

        df.loc[
            mask,
            "STATUS_RESOLUCAO",
        ] = "PENDENTE"

        df.loc[
            mask,
            "CONFIANCA_FINAL",
        ] = "BAIXA"

    # Imobiliário

    for cd_cvm in IMOBILIARIAS:

        alterar_motor(
            df,
            cd_cvm,
            "IMOBILIARIO",
            "ATIVIDADE_IMOBILIARIA_EXPLICITA",
        )

    # Operacionais explicitamente resolvidos

    for cd_cvm, motivo in (
        OPERACIONAIS_RESOLVIDOS.items()
    ):

        alterar_motor(
            df,
            cd_cvm,
            "OPERACIONAL",
            (
                "ATIVIDADE_OPERACIONAL_EXPLICITA__"
                + motivo
            ),
        )

    # ========================================================
    # CELL 12 — CORREÇÃO AEGEA
    # ========================================================

    mask_aegea = df["CD_CVM"].eq(23396)

    if int(mask_aegea.sum()) == 1:

        df.loc[
            mask_aegea,
            "MOTOR_FINAL",
        ] = "UTILITY"

        df.loc[
            mask_aegea,
            "REGRA_RESOLUCAO",
        ] = "CORRECAO_AEGEA_SANEAMENTO_MISTO"

        df.loc[
            mask_aegea,
            "STATUS_RESOLUCAO",
        ] = "RESOLVIDO"

        df.loc[
            mask_aegea,
            "CONFIANCA_FINAL",
        ] = "ALTA"

    # ========================================================
    # PENDÊNCIAS
    # ========================================================

    mask_pendente = (
        df["MOTOR_FINAL"]
        .eq("AUDITAR")
    )

    df.loc[
        mask_pendente,
        "STATUS_RESOLUCAO",
    ] = "PENDENTE"

    df.loc[
        mask_pendente,
        "CONFIANCA_FINAL",
    ] = "BAIXA"

    # ========================================================
    # SUBTIPO
    # ========================================================

    df["SUBTIPO_ECONOMICO"] = (
        df["MOTOR_FINAL"]
        .map(SUBTIPOS)
    )

    if int(mask_aegea.sum()) == 1:

        df.loc[
            mask_aegea,
            "SUBTIPO_ECONOMICO",
        ] = "SANEAMENTO_MISTO"

    # ========================================================
    # ELEGIBILIDADE DA ARQUITETURA
    # ========================================================

    df["ARQUITETURA_APTA_SCORE"] = (
        ~df["MOTOR_FINAL"]
        .eq("AUDITAR")
    )

    df["STATUS_ARQUITETURA"] = np.where(
        df["ARQUITETURA_APTA_SCORE"],
        "CONGELADA_UTILIZAVEL",
        "PENDENTE_AUDITORIA",
    )

    df["MOTOR_ALTERADO"] = (
        df["MOTOR_ORIGINAL"]
        !=
        df["MOTOR_FINAL"]
    )

    # ========================================================
    # INTEGRIDADE
    # ========================================================

    invalid = (
        set(
            df["MOTOR_FINAL"]
            .dropna()
            .unique()
        )
        - VALID_ENGINES
    )

    if invalid:

        raise RuntimeError(
            "Motor setorial inválido: "
            + ", ".join(sorted(invalid))
        )

    if df["MOTOR_FINAL"].isna().any():

        raise RuntimeError(
            "Empresa sem MOTOR_FINAL."
        )

    if df["CD_CVM"].duplicated().any():

        raise RuntimeError(
            "CD_CVM duplicado após Sector Engine."
        )

    return df


# ============================================================
# 10. TESTE INTERNO
# ============================================================

def _self_test():

    assert (
        normalizar_texto(
            "Energia Elétrica"
        )
        == "ENERGIA ELETRICA"
    )

    assert (
        normalizar_texto(
            "Saneamento, Serv. Água e Gás"
        )
        == "SANEAMENTO, SERV. AGUA E GAS"
    )

    assert (
        "UTILITY"
        in VALID_ENGINES
    )

    assert (
        "AUDITAR"
        in VALID_ENGINES
    )

    assert (
        SUBTIPOS[
            "FINANCEIRO_BANCO"
        ]
        == "BANCO_OU_INTERMEDIACAO"
    )

    print(
        "sector_engine_v1.py: "
        "SELF TEST OK"
    )


if __name__ == "__main__":
    _self_test()
