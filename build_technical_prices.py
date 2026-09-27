# ============================================================
# B3_INVESTMENT_ENGINE
# build_technical_prices.py
#
# Constrói:
# data/technical_prices.csv
#
# FONTE CONGELADA:
# technical_cell06b_raw_indicators_adjusted.csv
#
# PRINCÍPIO:
# O robô NÃO recalcula os indicadores validados no estudo.
# Ele transporta para produção exatamente os indicadores
# calculados no checkpoint Cell06B, após:
#
# - ajustes de eventos corporativos;
# - tratamento de descontinuidades residuais;
# - segmentação técnica;
# - cálculo dos indicadores.
#
# NÃO:
# - cria Technical Score
# - cria sinal de compra/venda
# - cria gatilho obrigatório
# - refaz pesquisa OOS
# - recupera empresa reprovada nos fundamentos
# ============================================================

from pathlib import Path
import pandas as pd


# ============================================================
# 1. DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. CHECKPOINT TÉCNICO CONGELADO
# ============================================================
#
# Este é o checkpoint validado no estudo.
#
# Não existe seleção automática de arquivos.
# Se este arquivo não existir, o processo deve falhar.
# ============================================================

SOURCE_FILE = Path(
    "/content/drive/MyDrive/"
    "b3_quant_study/"
    "technical_timing_engine/"
    "technical_cell06b_raw_indicators_adjusted.csv"
)


# ============================================================
# 3. SAÍDA
# ============================================================

OUTPUT_FILE = DATA_DIR / "technical_prices.csv"


# ============================================================
# 4. COLUNAS DE PRODUÇÃO
# ============================================================
#
# Os sete indicadores abaixo são exatamente os selecionados
# pelo estudo técnico.
#
# TECH_SEGMENT_ID é preservado para manter a identidade
# da segmentação utilizada no cálculo original.
#
# CD_CVM é preservado como identidade da companhia.
# ============================================================

IDENTITY_COLUMNS = [
    "CD_CVM",
    "TICKER",
    "DATE",
    "TECH_SEGMENT_ID",
]

PRICE_COLUMNS = [
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
]

TECHNICAL_INDICATORS = [
    "SMA200_SLOPE_20D",
    "ATR_PCT",
    "ROC_60",
    "MACD_HIST_PCT",
    "DIST_SMA_200",
    "BB_WIDTH",
    "DIST_SMA_50",
]

OUTPUT_COLUMNS = (
    IDENTITY_COLUMNS
    + PRICE_COLUMNS
    + TECHNICAL_INDICATORS
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

        for column in df.columns
    ]

    return df


# ============================================================
# 6. VALIDAR CHECKPOINT
# ============================================================

def validate_source_file():

    if not SOURCE_FILE.exists():

        raise FileNotFoundError(
            "\nCheckpoint técnico congelado não encontrado:\n\n"
            f"{SOURCE_FILE}\n\n"
            "Monte o Google Drive no Colab e confirme que o "
            "checkpoint Cell06B está disponível.\n\n"
            "Nenhum checkpoint alternativo será selecionado "
            "automaticamente."
        )

    print("Checkpoint técnico congelado:")
    print(SOURCE_FILE)


# ============================================================
# 7. CARREGAR CHECKPOINT
# ============================================================

def load_source_data():

    print("\n" + "=" * 80)
    print("CARREGANDO CELL06B CONGELADO")
    print("=" * 80)

    df = pd.read_csv(
        SOURCE_FILE,
        low_memory=False,
    )

    df = normalize_columns(df)

    print("Linhas:", len(df))
    print("Colunas:", len(df.columns))

    return df


# ============================================================
# 8. VALIDAR ESTRUTURA
# ============================================================

def validate_required_columns(df):

    missing = [
        column
        for column in OUTPUT_COLUMNS
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "\nCheckpoint Cell06B incompatível.\n\n"
            "Colunas obrigatórias ausentes:\n"
            + "\n".join(
                f"- {column}"
                for column in missing
            )
        )

    print("\n✓ Estrutura Cell06B validada.")
    print(
        "✓ 7 indicadores técnicos do estudo encontrados."
    )


# ============================================================
# 9. EXTRAIR CAMPOS DE PRODUÇÃO
# ============================================================

def extract_production_data(df):

    result = df[
        OUTPUT_COLUMNS
    ].copy()

    return result


# ============================================================
# 10. LIMPEZA MECÂNICA
# ============================================================
#
# IMPORTANTE:
#
# Não recalculamos indicadores.
# Não alteramos segmentação.
# Não preenchemos NaN dos indicadores.
#
# NaN pode ser legítimo no início de uma janela técnica.
# ============================================================

def clean_production_data(df):

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

    numeric_columns = (
        ["CD_CVM"]
        + PRICE_COLUMNS
        + TECHNICAL_INDICATORS
    )

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # --------------------------------------------------------
    # Remover somente registros estruturalmente inválidos.
    #
    # Indicadores técnicos NÃO fazem parte do dropna.
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "CD_CVM",
            "TICKER",
            "DATE",
            "TECH_SEGMENT_ID",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
        ]
    )

    # --------------------------------------------------------
    # OHLC positivo
    # --------------------------------------------------------

    df = df[
        (df["OPEN"] > 0)
        & (df["HIGH"] > 0)
        & (df["LOW"] > 0)
        & (df["CLOSE"] > 0)
    ]

    # --------------------------------------------------------
    # Integridade OHLC
    # --------------------------------------------------------

    df = df[
        df["HIGH"] >= df["LOW"]
    ]

    # --------------------------------------------------------
    # Ordenação
    # --------------------------------------------------------

    df = (
        df
        .sort_values(
            [
                "CD_CVM",
                "TICKER",
                "DATE",
            ]
        )
        .drop_duplicates(
            subset=[
                "CD_CVM",
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
        DATA_DIR
        / "fundamental_input.csv"
    )

    if not fundamental_file.exists():

        raise FileNotFoundError(
            "\nArquivo ainda não existe:\n\n"
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

        for column in fundamental.columns
    ]

    if "TICKER" not in fundamental.columns:

        raise ValueError(
            "fundamental_input.csv "
            "não possui TICKER."
        )

    tickers = (
        fundamental["TICKER"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .drop_duplicates()
        .tolist()
    )

    return tickers


# ============================================================
# 12. FILTRAR UNIVERSO DE PRODUÇÃO
# ============================================================
#
# Mantemos somente empresas pertencentes ao universo
# fundamental recebido pelo engine.
#
# O técnico não cria universo próprio.
# ============================================================

def filter_production_universe(
    technical,
    fundamental_tickers,
):

    filtered = technical[
        technical["TICKER"].isin(
            fundamental_tickers
        )
    ].copy()

    return filtered


# ============================================================
# 13. AUDITORIA DOS INDICADORES
# ============================================================

def audit_indicators(df):

    print("\n" + "=" * 80)
    print("AUDITORIA DOS 7 INDICADORES")
    print("=" * 80)

    for indicator in TECHNICAL_INDICATORS:

        available = (
            df[indicator]
            .notna()
            .sum()
        )

        missing = (
            df[indicator]
            .isna()
            .sum()
        )

        print(
            f"{indicator:<22} "
            f"válidos={available:<8} "
            f"NaN={missing}"
        )


# ============================================================
# 14. AUDITORIA DA BASE TÉCNICA
# ============================================================

def audit_technical_data(
    technical,
    fundamental_tickers,
):

    print("\n" + "=" * 80)
    print("AUDITORIA DA BASE TÉCNICA")
    print("=" * 80)

    technical_tickers = set(
        technical["TICKER"].unique()
    )

    fundamental_set = set(
        fundamental_tickers
    )

    missing = sorted(
        fundamental_set
        - technical_tickers
    )

    print(
        "Empresas fundamentais:",
        len(fundamental_set),
    )

    print(
        "Empresas com histórico técnico:",
        len(technical_tickers),
    )

    print(
        "Empresas sem histórico técnico:",
        len(missing),
    )

    print(
        "Registros técnicos:",
        len(technical),
    )

    print(
        "Segmentos técnicos:",
        technical["TECH_SEGMENT_ID"].nunique(),
    )

    print(
        "CD_CVM distintos:",
        technical["CD_CVM"].nunique(),
    )

    if missing:

        print(
            "\nTickers sem histórico técnico:"
        )

        print(
            ", ".join(missing)
        )

        print(
            "\nATENÇÃO:"
        )

        print(
            "Ausência de contexto técnico não reprova "
            "uma empresa fundamentalmente aprovada."
        )

    # --------------------------------------------------------
    # Duplicidade
    # --------------------------------------------------------

    duplicates = technical.duplicated(
        subset=[
            "CD_CVM",
            "TICKER",
            "DATE",
        ]
    ).sum()

    if duplicates:

        raise RuntimeError(
            "Foram encontradas duplicidades "
            "CD_CVM/TICKER/DATE."
        )

    # --------------------------------------------------------
    # Integridade OHLC
    # --------------------------------------------------------

    invalid_ohlc = technical[
        technical["HIGH"]
        < technical["LOW"]
    ]

    if not invalid_ohlc.empty:

        raise RuntimeError(
            "Foram encontrados registros OHLC "
            "estruturalmente inválidos."
        )

    audit_indicators(
        technical
    )

    return {
        "missing_tickers": missing,
    }


# ============================================================
# 15. AUDITORIA DE FIDELIDADE
# ============================================================
#
# Garante que os indicadores presentes na saída são cópias
# dos valores do checkpoint, não recálculos.
# ============================================================

def audit_fidelity(
    source,
    output,
):

    print("\n" + "=" * 80)
    print("AUDITORIA DE FIDELIDADE CELL06B")
    print("=" * 80)

    source_keys = source[
        [
            "CD_CVM",
            "TICKER",
            "DATE",
        ]
        + TECHNICAL_INDICATORS
    ].copy()

    source_keys["TICKER"] = (
        source_keys["TICKER"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    source_keys["DATE"] = pd.to_datetime(
        source_keys["DATE"],
        errors="coerce",
    )

    merged = output.merge(
        source_keys,
        on=[
            "CD_CVM",
            "TICKER",
            "DATE",
        ],
        how="left",
        suffixes=(
            "_OUTPUT",
            "_SOURCE",
        ),
        validate="one_to_one",
    )

    divergences = {}

    for indicator in TECHNICAL_INDICATORS:

        output_col = (
            f"{indicator}_OUTPUT"
        )

        source_col = (
            f"{indicator}_SOURCE"
        )

        left = pd.to_numeric(
            merged[output_col],
            errors="coerce",
        )

        right = pd.to_numeric(
            merged[source_col],
            errors="coerce",
        )

        both_nan = (
            left.isna()
            & right.isna()
        )

        equal = (
            (left == right)
            | both_nan
        )

        count = int(
            (~equal).sum()
        )

        divergences[indicator] = count

    total_divergences = sum(
        divergences.values()
    )

    for indicator, count in divergences.items():

        print(
            f"{indicator:<22} "
            f"divergências={count}"
        )

    if total_divergences != 0:

        raise RuntimeError(
            "\nFalha de fidelidade:\n"
            "a saída técnica diverge dos indicadores "
            "congelados do Cell06B."
        )

    print(
        "\n✓ Fidelidade confirmada."
    )

    print(
        "✓ Nenhum dos 7 indicadores foi recalculado."
    )

    print(
        "✓ Valores idênticos ao checkpoint Cell06B."
    )


# ============================================================
# 16. EXECUÇÃO
# ============================================================

def main():

    print("=" * 80)
    print("B3 INVESTMENT ENGINE")
    print("BUILD TECHNICAL DATA — CELL06B")
    print("=" * 80)

    # --------------------------------------------------------
    # Checkpoint congelado
    # --------------------------------------------------------

    validate_source_file()

    source = load_source_data()

    validate_required_columns(
        source
    )

    # --------------------------------------------------------
    # Extração
    # --------------------------------------------------------

    technical = (
        extract_production_data(
            source
        )
    )

    technical = (
        clean_production_data(
            technical
        )
    )

    # --------------------------------------------------------
    # Universo fundamental
    # --------------------------------------------------------

    fundamental_tickers = (
        load_fundamental_universe()
    )

    # --------------------------------------------------------
    # Universo de produção
    # --------------------------------------------------------

    technical = (
        filter_production_universe(
            technical,
            fundamental_tickers,
        )
    )

    # --------------------------------------------------------
    # Auditorias
    # --------------------------------------------------------

    audit_technical_data(
        technical,
        fundamental_tickers,
    )

    audit_fidelity(
        source,
        technical,
    )

    # --------------------------------------------------------
    # Salvar
    # --------------------------------------------------------

    technical.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 80)

    print(
        "✓ technical_prices.csv criado."
    )

    print(
        "✓ Fonte: Cell06B congelado."
    )

    print(
        "✓ CD_CVM preservado."
    )

    print(
        "✓ TECH_SEGMENT_ID preservado."
    )

    print(
        "✓ 7 indicadores do estudo preservados."
    )

    print(
        "✓ Nenhum indicador técnico recalculado."
    )

    print(
        "✓ Nenhum Technical Score criado."
    )

    print(
        "✓ Nenhum gatilho técnico obrigatório criado."
    )

    print(
        "✓ Técnico permanece apenas como contexto."
    )

    print(
        "\nArquivo criado:"
    )

    print(
        OUTPUT_FILE
    )

    print("=" * 80)


# ============================================================
# 17. START
# ============================================================

if __name__ == "__main__":

    main()
