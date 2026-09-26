from pathlib import Path
import pandas as pd


# ============================================================
# B3_INVESTMENT_ENGINE
# build_fundamental_input.py
#
# Constrói o arquivo:
# data/fundamental_input.csv
#
# usando exclusivamente os checkpoints reais e congelados
# do estudo fundamentalista.
# ============================================================


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CAMINHO DOS CHECKPOINTS
# ============================================================
#
# Ao executar no Colab, altere CHECKPOINT_DIR para o diretório
# real onde estão os checkpoints congelados.
# ============================================================

CHECKPOINT_DIR = Path(
    "/content/drive/MyDrive/"
    "b3_quant_study/"
    "checkpoints_quality_engine"
)


QUALITY_FILE = (
    CHECKPOINT_DIR /
    "cell18_quality_engine.csv"
)

INVESTABILITY_FILE = (
    CHECKPOINT_DIR /
    "cell19_b3_investability_approved.csv"
)

VALUATION_FILE = (
    CHECKPOINT_DIR /
    "cell33c_valuation_score_2026_final.csv"
)

RANKING_FILE = (
    CHECKPOINT_DIR /
    "cell34_fundamental_ranking_2026.csv"
)


OUTPUT_FILE = (
    DATA_DIR /
    "fundamental_input.csv"
)


# ============================================================
# UTILIDADES
# ============================================================

def normalize_columns(df):

    df = df.copy()

    df.columns = [
        str(col)
        .strip()
        .upper()
        for col in df.columns
    ]

    return df


def find_column(
    df,
    candidates,
    required=True,
):

    for candidate in candidates:

        if candidate in df.columns:

            return candidate

    if required:

        raise ValueError(
            "Nenhuma das colunas esperadas foi encontrada: "
            f"{candidates}\n\n"
            f"Colunas disponíveis:\n"
            f"{list(df.columns)}"
        )

    return None


def load_csv(path):

    if not path.exists():

        raise FileNotFoundError(
            f"Arquivo não encontrado:\n{path}"
        )

    df = pd.read_csv(
        path,
        low_memory=False
    )

    return normalize_columns(df)


# ============================================================
# CARREGAR CHECKPOINTS
# ============================================================

print("=" * 80)
print("B3 INVESTMENT ENGINE")
print("BUILD FUNDAMENTAL INPUT")
print("=" * 80)


quality = load_csv(
    QUALITY_FILE
)

investability = load_csv(
    INVESTABILITY_FILE
)

valuation = load_csv(
    VALUATION_FILE
)

ranking = load_csv(
    RANKING_FILE
)


print(
    "Quality:",
    len(quality)
)

print(
    "Investability:",
    len(investability)
)

print(
    "Valuation:",
    len(valuation)
)

print(
    "Ranking:",
    len(ranking)
)


# ============================================================
# IDENTIFICAR TICKER
# ============================================================

ticker_candidates = [
    "TICKER",
    "CODIGO",
    "CÓDIGO",
    "SYMBOL",
]


quality_ticker = find_column(
    quality,
    ticker_candidates
)

investability_ticker = find_column(
    investability,
    ticker_candidates
)

valuation_ticker = find_column(
    valuation,
    ticker_candidates
)

ranking_ticker = find_column(
    ranking,
    ticker_candidates
)


quality = quality.rename(
    columns={
        quality_ticker:
            "TICKER"
    }
)

investability = investability.rename(
    columns={
        investability_ticker:
            "TICKER"
    }
)

valuation = valuation.rename(
    columns={
        valuation_ticker:
            "TICKER"
    }
)

ranking = ranking.rename(
    columns={
        ranking_ticker:
            "TICKER"
    }
)


for df in [
    quality,
    investability,
    valuation,
    ranking,
]:

    df["TICKER"] = (
        df["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )


# ============================================================
# QUALITY SCORE
# ============================================================

quality_score_column = find_column(
    quality,
    [
        "QUALITY_SCORE",
        "QUALITY_SCORE_V1",
        "SCORE_QUALITY",
    ]
)


quality_base = (
    quality[
        [
            "TICKER",
            quality_score_column,
        ]
    ]
    .rename(
        columns={
            quality_score_column:
                "QUALITY_SCORE"
        }
    )
    .drop_duplicates(
        subset="TICKER"
    )
)


# ============================================================
# HISTÓRICO
# ============================================================

history_column = find_column(
    investability,
    [
        "HISTORY_YEARS",
        "YEARS_HISTORY",
        "LISTED_YEARS",
        "TRADING_YEARS",
        "ANOS_HISTORICO",
        "ANOS_LISTADA",
    ],
    required=False,
)


# ============================================================
# LIQUIDEZ
# ============================================================

liquidity_column = find_column(
    investability,
    [
        "AVG_DAILY_LIQUIDITY_BRL",
        "AVG_DAILY_LIQUIDITY",
        "AVERAGE_DAILY_LIQUIDITY",
        "LIQUIDITY_BRL",
        "LIQUIDEZ_MEDIA_DIARIA",
        "LIQUIDEZ_MEDIA",
    ],
    required=False,
)


if history_column is None:

    raise ValueError(
        "\nNão encontrei a coluna de anos de histórico "
        "em cell19_b3_investability_approved.csv.\n\n"
        "Não será criado valor artificial.\n"
        "Verifique as colunas mostradas acima."
    )


if liquidity_column is None:

    raise ValueError(
        "\nNão encontrei a coluna de liquidez média diária "
        "em cell19_b3_investability_approved.csv.\n\n"
        "Não será criado valor artificial."
    )


investability_base = (
    investability[
        [
            "TICKER",
            history_column,
            liquidity_column,
        ]
    ]
    .rename(
        columns={
            history_column:
                "HISTORY_YEARS",

            liquidity_column:
                "AVG_DAILY_LIQUIDITY_BRL",
        }
    )
    .drop_duplicates(
        subset="TICKER"
    )
)


# ============================================================
# VALUATION SCORE
# ============================================================

valuation_score_column = find_column(
    valuation,
    [
        "VALUATION_SCORE_2026",
        "VALUATION_SCORE",
        "SCORE_VALUATION",
    ]
)


valuation_base = (
    valuation[
        [
            "TICKER",
            valuation_score_column,
        ]
    ]
    .rename(
        columns={
            valuation_score_column:
                "VALUATION_SCORE"
        }
    )
    .drop_duplicates(
        subset="TICKER"
    )
)


# ============================================================
# UNIVERSO OFICIAL
# ============================================================
#
# Cell34 é usado como universo final da integração
# fundamental.
# ============================================================

universe = (
    ranking[
        ["TICKER"]
    ]
    .drop_duplicates()
    .copy()
)


# ============================================================
# INTEGRAÇÃO
# ============================================================

final = (
    universe
    .merge(
        quality_base,
        on="TICKER",
        how="left",
        validate="one_to_one",
    )
    .merge(
        investability_base,
        on="TICKER",
        how="left",
        validate="one_to_one",
    )
    .merge(
        valuation_base,
        on="TICKER",
        how="left",
        validate="one_to_one",
    )
)


# ============================================================
# CONVERSÃO NUMÉRICA
# ============================================================

numeric_columns = [
    "QUALITY_SCORE",
    "HISTORY_YEARS",
    "AVG_DAILY_LIQUIDITY_BRL",
    "VALUATION_SCORE",
]


for column in numeric_columns:

    final[column] = pd.to_numeric(
        final[column],
        errors="coerce"
    )


# ============================================================
# AUDITORIA
# ============================================================

print("\n" + "=" * 80)
print("AUDITORIA")
print("=" * 80)


print(
    "Empresas no universo final:",
    len(final)
)


print(
    "Quality Score disponível:",
    final[
        "QUALITY_SCORE"
    ]
    .notna()
    .sum()
)


print(
    "Histórico disponível:",
    final[
        "HISTORY_YEARS"
    ]
    .notna()
    .sum()
)


print(
    "Liquidez disponível:",
    final[
        "AVG_DAILY_LIQUIDITY_BRL"
    ]
    .notna()
    .sum()
)


print(
    "Valuation disponível:",
    final[
        "VALUATION_SCORE"
    ]
    .notna()
    .sum()
)


print(
    "Valuation pendente:",
    final[
        "VALUATION_SCORE"
    ]
    .isna()
    .sum()
)


# ============================================================
# TESTE DO FUNIL CONGELADO
# ============================================================

if len(final) != 55:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        f"Esperávamos 55 empresas investíveis, "
        f"mas foram encontradas {len(final)}.\n"
        "O arquivo não será considerado validado."
    )


valuation_count = int(
    final[
        "VALUATION_SCORE"
    ]
    .notna()
    .sum()
)


pending_count = int(
    final[
        "VALUATION_SCORE"
    ]
    .isna()
    .sum()
)


if valuation_count != 48:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        f"Esperávamos 48 valuations concluídos. "
        f"Encontrados: {valuation_count}"
    )


if pending_count != 7:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        f"Esperávamos 7 valuations pendentes. "
        f"Encontrados: {pending_count}"
    )


# ============================================================
# QUALITY GATE
# ============================================================

invalid_quality = final[
    final[
        "QUALITY_SCORE"
    ] < 60
]


if len(invalid_quality) > 0:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        "Foi encontrada empresa abaixo do "
        "Quality Gate 60 no universo final."
    )


# ============================================================
# INVESTABILITY
# ============================================================

invalid_history = final[
    final[
        "HISTORY_YEARS"
    ] < 10
]


if len(invalid_history) > 0:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        "Foi encontrada empresa com menos de "
        "10 anos no universo investível."
    )


invalid_liquidity = final[
    final[
        "AVG_DAILY_LIQUIDITY_BRL"
    ] < 6_000_000
]


if len(invalid_liquidity) > 0:

    raise RuntimeError(
        "\nAUDITORIA FALHOU.\n"
        "Foi encontrada empresa abaixo de "
        "R$ 6 milhões de liquidez média diária."
    )


# ============================================================
# ORDENAR PELO SCORE FUNDAMENTAL CONGELADO
# ============================================================

final_score_column = find_column(
    ranking,
    [
        "FUNDAMENTAL_SCORE",
        "FINAL_SCORE",
        "SCORE_FINAL",
        "FUNDAMENTAL_SCORE_2026",
    ],
    required=False,
)


if final_score_column is not None:

    ranking_score = (
        ranking[
            [
                "TICKER",
                final_score_column,
            ]
        ]
        .rename(
            columns={
                final_score_column:
                    "_FROZEN_FINAL_SCORE"
            }
        )
        .drop_duplicates(
            subset="TICKER"
        )
    )

    final = final.merge(
        ranking_score,
        on="TICKER",
        how="left",
        validate="one_to_one",
    )

    final = (
        final
        .sort_values(
            "_FROZEN_FINAL_SCORE",
            ascending=False,
            na_position="last",
        )
        .drop(
            columns=[
                "_FROZEN_FINAL_SCORE"
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# COLUNAS FINAIS EXATAS ESPERADAS PELO main.py
# ============================================================

final = final[
    [
        "TICKER",
        "QUALITY_SCORE",
        "HISTORY_YEARS",
        "AVG_DAILY_LIQUIDITY_BRL",
        "VALUATION_SCORE",
    ]
]


# ============================================================
# SALVAR
# ============================================================

final.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig",
)


print("\n" + "=" * 80)

print(
    "✓ fundamental_input.csv criado."
)

print(
    "✓ 55 empresas investíveis preservadas."
)

print(
    "✓ 48 valuations concluídos preservados."
)

print(
    "✓ 7 valuations pendentes preservados."
)

print(
    "✓ Quality Gate >= 60 preservado."
)

print(
    "✓ Histórico mínimo de 10 anos preservado."
)

print(
    "✓ Liquidez mínima de R$ 6 milhões preservada."
)

print(
    "✓ Nenhum dado fundamental foi inventado."
)

print("\nArquivo criado:")

print(
    OUTPUT_FILE
)

print("=" * 80)
