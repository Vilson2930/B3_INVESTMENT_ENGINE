# ============================================================
# B3_INVESTMENT_ENGINE
# build_technical_prices.py
#
# Constrói:
# data/technical_prices.csv
#
# a partir da base histórica REAL utilizada no estudo
# do Technical Timing Engine.
#
# IMPORTANTE:
# - não cria Technical Score
# - não cria sinal de compra/venda
# - não cria gatilho obrigatório
# - não refaz a pesquisa OOS
# - apenas prepara preços para o motor técnico de produção
# ============================================================

from pathlib import Path
import pandas as pd


# ============================================================
# 1. DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = (
    BASE_DIR /
    "data"
)

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. BASE DO ESTUDO TÉCNICO
# ============================================================
#
# Diretório congelado utilizado no projeto.
# ============================================================

TECHNICAL_STUDY_DIR = Path(
    "/content/drive/MyDrive/"
    "b3_quant_study/"
    "technical_timing_engine"
)


# ============================================================
# 3. POSSÍVEIS CHECKPOINTS COM PREÇOS
# ============================================================
#
# O script NÃO escolhe dados artificiais.
#
# Ele procura arquivos reais do estudo que contenham:
#
# TICKER
# DATE
# OPEN
# HIGH
# LOW
# CLOSE
#
# ============================================================

CANDIDATE_FILES = [

    TECHNICAL_STUDY_DIR /
    "technical_cell06b_segmented_prices.csv",

    TECHNICAL_STUDY_DIR /
    "technical_cell06b_prices_segmented.csv",

    TECHNICAL_STUDY_DIR /
    "technical_cell05b_adjusted_prices.csv",

    TECHNICAL_STUDY_DIR /
    "technical_cell05b_prices_adjusted.csv",

    TECHNICAL_STUDY_DIR /
    "technical_prices_adjusted.csv",

    TECHNICAL_STUDY_DIR /
    "technical_prices.csv",
]


# ============================================================
# 4. SAÍDA
# ============================================================

OUTPUT_FILE = (
    DATA_DIR /
    "technical_prices.csv"
)


# ============================================================
# 5. NORMALIZAR COLUNAS
# ============================================================

def normalize_columns(df):

    df = df.copy()

    df.columns = [

        str(column)
        .strip()
        .upper()

        for column
        in df.columns
    ]

    return df


# ============================================================
# 6. LOCALIZAR COLUNA
# ============================================================

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

            "\nColuna obrigatória não encontrada.\n\n"

            f"Candidatas:\n{candidates}\n\n"

            f"Colunas existentes:\n"
            f"{list(df.columns)}"
        )

    return None


# ============================================================
# 7. LOCALIZAR BASE REAL
# ============================================================

def locate_price_file():

    # --------------------------------------------------------
    # Primeiro tenta nomes conhecidos.
    # --------------------------------------------------------

    for path in CANDIDATE_FILES:

        if path.exists():

            print(
                "Base encontrada:"
            )

            print(
                path
            )

            return path

    # --------------------------------------------------------
    # Se os nomes forem diferentes, procura CSVs existentes
    # dentro da pasta técnica.
    # --------------------------------------------------------

    if not TECHNICAL_STUDY_DIR.exists():

        raise FileNotFoundError(

            "\nDiretório técnico não encontrado:\n"

            f"{TECHNICAL_STUDY_DIR}\n\n"

            "Monte o Google Drive no Colab antes "
            "de executar este script."
        )

    csv_files = list(
        TECHNICAL_STUDY_DIR.glob(
            "*.csv"
        )
    )

    print(
        "\nArquivos CSV encontrados:",
        len(csv_files)
    )

    # --------------------------------------------------------
    # Procurar somente arquivos que realmente possuam
    # estrutura OHLC.
    # --------------------------------------------------------

    valid_candidates = []

    for path in csv_files:

        try:

            sample = pd.read_csv(
                path,
                nrows=5,
                low_memory=False,
            )

            sample = normalize_columns(
                sample
            )

            columns = set(
                sample.columns
            )

            has_ticker = bool(
                columns.intersection({
                    "TICKER",
                    "SYMBOL",
                    "CODIGO",
                    "CÓDIGO",
                })
            )

            has_date = bool(
                columns.intersection({
                    "DATE",
                    "DATA",
                    "DATETIME",
                    "TIMESTAMP",
                })
            )

            has_open = bool(
                columns.intersection({
                    "OPEN",
                    "ABERTURA",
                })
            )

            has_high = bool(
                columns.intersection({
                    "HIGH",
                    "MAX",
                    "MAXIMA",
                    "MÁXIMA",
                })
            )

            has_low = bool(
                columns.intersection({
                    "LOW",
                    "MIN",
                    "MINIMA",
                    "MÍNIMA",
                })
            )

            has_close = bool(
                columns.intersection({
                    "CLOSE",
                    "ADJ_CLOSE",
                    "ADJCLOSE",
                    "FECHAMENTO",
                })
            )

            if (
                has_ticker
                and has_date
                and has_open
                and has_high
                and has_low
                and has_close
            ):

                valid_candidates.append(
                    path
                )

        except Exception:

            continue

    if not valid_candidates:

        raise FileNotFoundError(

            "\nNenhum checkpoint com preços OHLC "
            "foi localizado automaticamente.\n\n"

            "Nenhum dado será inventado.\n"
            "Precisamos usar a base real do estudo técnico."
        )

    # --------------------------------------------------------
    # Se existir apenas uma base compatível, ela é usada.
    # --------------------------------------------------------

    if len(valid_candidates) == 1:

        print(
            "\nBase OHLC identificada:"
        )

        print(
            valid_candidates[0]
        )

        return valid_candidates[0]

    # --------------------------------------------------------
    # Se houver várias bases, preferimos a mais avançada
    # metodologicamente pelo nome.
    # --------------------------------------------------------

    priority_terms = [

        "06b",
        "segmented",
        "segmentado",
        "05b",
        "adjusted",
        "ajustado",
    ]

    for term in priority_terms:

        matches = [

            path

            for path
            in valid_candidates

            if term.lower()
            in path.name.lower()
        ]

        if len(matches) == 1:

            print(
                "\nBase selecionada:"
            )

            print(
                matches[0]
            )

            return matches[0]

    # --------------------------------------------------------
    # Ambiguidade real:
    # não escolhemos silenciosamente.
    # --------------------------------------------------------

    message = (

        "\nForam encontradas várias bases OHLC "
        "compatíveis.\n\n"

        "Para preservar a metodologia, o script "
        "não escolherá arbitrariamente.\n\n"

        "Arquivos encontrados:\n"
    )

    for path in valid_candidates:

        message += (
            f"\n- {path.name}"
        )

    raise RuntimeError(
        message
    )


# ============================================================
# 8. CARREGAR BASE
# ============================================================

def load_price_data(
    path
):

    print("\n" + "=" * 80)

    print(
        "CARREGANDO BASE TÉCNICA"
    )

    print("=" * 80)

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    df = normalize_columns(
        df
    )

    print(
        "Linhas:",
        len(df)
    )

    print(
        "Colunas:",
        len(df.columns)
    )

    return df


# ============================================================
# 9. PADRONIZAR COLUNAS
# ============================================================

def standardize_price_data(
    df
):

    ticker_col = find_column(

        df,

        [
            "TICKER",
            "SYMBOL",
            "CODIGO",
            "CÓDIGO",
        ],
    )

    date_col = find_column(

        df,

        [
            "DATE",
            "DATA",
            "DATETIME",
            "TIMESTAMP",
        ],
    )

    open_col = find_column(

        df,

        [
            "OPEN",
            "ABERTURA",
        ],
    )

    high_col = find_column(

        df,

        [
            "HIGH",
            "MAX",
            "MAXIMA",
            "MÁXIMA",
        ],
    )

    low_col = find_column(

        df,

        [
            "LOW",
            "MIN",
            "MINIMA",
            "MÍNIMA",
        ],
    )

    # --------------------------------------------------------
    # CLOSE
    #
    # Preferência por preço ajustado quando ele já existir
    # na base validada do estudo.
    # --------------------------------------------------------

    close_col = find_column(

        df,

        [
            "ADJ_CLOSE",
            "ADJCLOSE",
            "CLOSE",
            "FECHAMENTO",
        ],
    )

    result = df[
        [
            ticker_col,
            date_col,
            open_col,
            high_col,
            low_col,
            close_col,
        ]
    ].copy()

    result.columns = [

        "TICKER",
        "DATE",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]

    return result


# ============================================================
# 10. LIMPEZA MECÂNICA
# ============================================================

def clean_price_data(
    df
):

    df = df.copy()

    df["TICKER"] = (
        df["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["DATE"] = pd.to_datetime(
        df["DATE"],
        errors="coerce",
    )

    numeric_columns = [

        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # --------------------------------------------------------
    # Remover apenas registros estruturalmente inválidos.
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "TICKER",
            "DATE",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
        ]
    )

    df = df[
        (
            df["OPEN"] > 0
        )
        &
        (
            df["HIGH"] > 0
        )
        &
        (
            df["LOW"] > 0
        )
        &
        (
            df["CLOSE"] > 0
        )
    ]

    df = df[
        df["HIGH"]
        >=
        df["LOW"]
    ]

    df = (
        df
        .sort_values(
            [
                "TICKER",
                "DATE",
            ]
        )
        .drop_duplicates(
            subset=[
                "TICKER",
                "DATE",
            ],
            keep="last",
        )
        .reset_index(
            drop=True
        )
    )

    return df


# ============================================================
# 11. CARREGAR UNIVERSO FUNDAMENTAL
# ============================================================

def load_fundamental_universe():

    fundamental_file = (
        DATA_DIR /
        "fundamental_input.csv"
    )

    if not fundamental_file.exists():

        raise FileNotFoundError(

            "\nArquivo ainda não existe:\n"

            f"{fundamental_file}\n\n"

            "Execute primeiro "
            "build_fundamental_input.py."
        )

    fundamental = pd.read_csv(
        fundamental_file,
        low_memory=False,
    )

    fundamental.columns = [

        str(column)
        .strip()
        .upper()

        for column
        in fundamental.columns
    ]

    if (
        "TICKER"
        not in fundamental.columns
    ):

        raise ValueError(
            "fundamental_input.csv "
            "não possui TICKER."
        )

    tickers = (

        fundamental[
            "TICKER"
        ]

        .astype(str)

        .str.strip()

        .str.upper()

        .dropna()

        .drop_duplicates()

        .tolist()
    )

    return tickers


# ============================================================
# 12. FILTRAR PARA O UNIVERSO DE PRODUÇÃO
# ============================================================

def filter_production_universe(
    prices,
    tickers
):

    filtered = prices[
        prices[
            "TICKER"
        ].isin(
            tickers
        )
    ].copy()

    return filtered


# ============================================================
# 13. AUDITORIA
# ============================================================

def audit_prices(
    prices,
    fundamental_tickers
):

    print("\n" + "=" * 80)

    print(
        "AUDITORIA DA BASE TÉCNICA"
    )

    print("=" * 80)

    price_tickers = set(
        prices[
            "TICKER"
        ].unique()
    )

    fundamental_set = set(
        fundamental_tickers
    )

    missing = sorted(
        fundamental_set
        -
        price_tickers
    )

    print(
        "Empresas fundamentais:",
        len(
            fundamental_set
        )
    )

    print(
        "Empresas com preços:",
        len(
            price_tickers
        )
    )

    print(
        "Empresas sem preços:",
        len(
            missing
        )
    )

    print(
        "Registros OHLC:",
        len(
            prices
        )
    )

    if missing:

        print(
            "\nTickers sem série técnica:"
        )

        print(
            ", ".join(
                missing
            )
        )

        print(
            "\nATENÇÃO:"
        )

        print(
            "Esses ativos NÃO serão "
            "reprovados pelo técnico."
        )

        print(
            "O Technical Timing Engine "
            "é apenas contexto."
        )

    # --------------------------------------------------------
    # Verificar quantidade mínima para SMA200 + slope 20d.
    # --------------------------------------------------------

    counts = (
        prices
        .groupby(
            "TICKER"
        )
        .size()
    )

    short_history = (
        counts[
            counts < 220
        ]
        .index
        .tolist()
    )

    if short_history:

        print(
            "\nSéries com menos de "
            "220 observações:"
        )

        print(
            ", ".join(
                short_history
            )
        )

        print(
            "\nEssas séries podem ficar "
            "sem contexto técnico completo."
        )

    # --------------------------------------------------------
    # Integridade OHLC
    # --------------------------------------------------------

    invalid_ohlc = prices[
        prices["HIGH"]
        <
        prices["LOW"]
    ]

    if not invalid_ohlc.empty:

        raise RuntimeError(
            "Foram encontrados registros "
            "OHLC estruturalmente inválidos."
        )

    return {
        "missing_tickers":
            missing,

        "short_history":
            short_history,
    }


# ============================================================
# 14. EXECUÇÃO
# ============================================================

def main():

    print("=" * 80)

    print(
        "B3 INVESTMENT ENGINE"
    )

    print(
        "BUILD TECHNICAL PRICES"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Base real do estudo
    # --------------------------------------------------------

    source_file = (
        locate_price_file()
    )

    raw = load_price_data(
        source_file
    )

    # --------------------------------------------------------
    # Padronização
    # --------------------------------------------------------

    prices = (
        standardize_price_data(
            raw
        )
    )

    prices = (
        clean_price_data(
            prices
        )
    )

    # --------------------------------------------------------
    # Universo fundamental
    # --------------------------------------------------------

    fundamental_tickers = (
        load_fundamental_universe()
    )

    # --------------------------------------------------------
    # Produção
    # --------------------------------------------------------

    prices = (
        filter_production_universe(
            prices,
            fundamental_tickers,
        )
    )

    # --------------------------------------------------------
    # Auditoria
    # --------------------------------------------------------

    audit_prices(
        prices,
        fundamental_tickers,
    )

    # --------------------------------------------------------
    # Salvar
    # --------------------------------------------------------

    prices.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 80)

    print(
        "✓ technical_prices.csv criado."
    )

    print(
        "✓ Base derivada do estudo técnico real."
    )

    print(
        "✓ Universo fundamental preservado."
    )

    print(
        "✓ Nenhum Technical Score criado."
    )

    print(
        "✓ Nenhum gatilho obrigatório criado."
    )

    print(
        "✓ Nenhuma empresa foi recuperada "
        "ou eliminada pelo técnico."
    )

    print(
        "\nArquivo criado:"
    )

    print(
        OUTPUT_FILE
    )

    print("=" * 80)


# ============================================================
# 15. START
# ============================================================

if __name__ == "__main__":

    main()
