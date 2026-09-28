
# ============================================================
# B3 INVESTMENT ENGINE
# INVESTABILITY ENGINE V1
# BASEADO NA CÉLULA 19 ORIGINAL
#
# REGRA PRESERVADA:
#   QUALITY
#       ↓
#   >= 10 ANOS DE NEGOCIAÇÃO
#       +
#   LIQUIDEZ MÉDIA >= R$ 6 MILHÕES/DIA
#
# NÃO CALCULA:
#   - valuation
#   - preço justo
#   - ranking
#   - score fundamental
#
# IMPORTANTE:
# As regras permanecem fixas.
# Os dados podem ser atualizados pelo chamador.
# ============================================================

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
import zipfile

import numpy as np
import pandas as pd


# ============================================================
# 1. NORMALIZAÇÃO
# ============================================================

def _norm19(value):

    if pd.isna(value):
        return ""

    value = str(value).upper().strip()

    value = "".join(
        c
        for c in unicodedata.normalize(
            "NFKD",
            value,
        )
        if not unicodedata.combining(c)
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    )


def _find_column(
    df: pd.DataFrame,
    candidates,
):

    normalized = {
        _norm19(c): c
        for c in df.columns
    }

    for candidate in candidates:

        key = _norm19(candidate)

        if key in normalized:
            return normalized[key]

    return None


# ============================================================
# 2. MAPA HISTÓRICO CD_CVM -> TICKER
# ============================================================

def _build_ticker_map(
    quality: pd.DataFrame,
    fca: pd.DataFrame,
):

    col_cd = _find_column(
        fca,
        [
            "CD_CVM",
            "CODIGO_CVM",
        ],
    )

    col_ticker = _find_column(
        fca,
        [
            "CODIGO_NEGOCIACAO",
            "CODIGO_NEGOCIACAO_VALOR_MOBILIARIO",
            "TICKER",
            "COD_NEGOCIACAO",
        ],
    )

    if col_cd is None:
        raise RuntimeError(
            "CD_CVM não localizado no checkpoint FCA."
        )

    if col_ticker is None:
        raise RuntimeError(
            "Coluna de ticker não localizada no checkpoint FCA."
        )

    mapa = fca[
        [
            col_cd,
            col_ticker,
        ]
    ].copy()

    mapa.columns = [
        "CD_CVM",
        "TICKER",
    ]

    mapa["CD_CVM"] = pd.to_numeric(
        mapa["CD_CVM"],
        errors="coerce",
    )

    mapa["TICKER"] = (
        mapa["TICKER"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # Somente formato plausível de ticker B3.
    mapa = mapa[
        mapa["TICKER"].str.match(
            r"^[A-Z]{4}[0-9]{1,2}$",
            na=False,
        )
    ].copy()

    mapa = mapa[
        ~mapa["TICKER"].isin(
            [
                "0000",
                "00000",
                "000000",
            ]
        )
    ]

    mapa = mapa.drop_duplicates(
        [
            "CD_CVM",
            "TICKER",
        ]
    )

    # Somente empresas aprovadas no Quality Engine.
    mapa = mapa[
        mapa["CD_CVM"].isin(
            quality["CD_CVM"]
        )
    ].copy()

    return mapa


# ============================================================
# 3. PARSER COTAHIST
# ============================================================

def _process_cotahist(
    caminho,
    tickers_alvo,
):

    encontrados = []

    with zipfile.ZipFile(
        caminho,
        "r",
    ) as z:

        arquivos = [
            n
            for n in z.namelist()
            if not n.endswith("/")
        ]

        if not arquivos:
            return encontrados

        nome = arquivos[0]

        with z.open(nome) as f:

            for raw in f:

                try:
                    linha = raw.decode(
                        "latin-1"
                    )
                except Exception:
                    continue

                if len(linha) < 188:
                    continue

                # Registro de cotação.
                if linha[0:2] != "01":
                    continue

                # Mercado à vista.
                if linha[24:27] != "010":
                    continue

                ticker = (
                    linha[12:24]
                    .strip()
                    .upper()
                )

                if ticker not in tickers_alvo:
                    continue

                try:

                    data = pd.to_datetime(
                        linha[2:10],
                        format="%Y%m%d",
                    )

                except Exception:

                    continue

                try:

                    voltot = (
                        int(
                            linha[170:188]
                        )
                        / 100
                    )

                except Exception:

                    voltot = np.nan

                encontrados.append(
                    (
                        ticker,
                        data,
                        voltot,
                    )
                )

    return encontrados


# ============================================================
# 4. CARREGAR COTAHIST
# ============================================================

def _load_cotahist(
    raw_b3: Path,
    ticker_map: pd.DataFrame,
    first_year: int = 2000,
    last_year: int = 2025,
):

    zips = []

    for year in range(
        first_year,
        last_year + 1,
    ):

        path = (
            raw_b3
            /
            f"COTAHIST_A{year}.ZIP"
        )

        if path.exists():

            zips.append(
                (
                    year,
                    path,
                )
            )

    if not zips:

        raise FileNotFoundError(
            "Nenhum COTAHIST encontrado."
        )

    tickers_alvo = set(
        ticker_map["TICKER"]
    )

    registros = []

    for year, path in zips:

        dados = _process_cotahist(
            path,
            tickers_alvo,
        )

        registros.extend(
            dados
        )

    cot = pd.DataFrame(
        registros,
        columns=[
            "TICKER",
            "DATA",
            "VOLTOT",
        ],
    )

    if cot.empty:

        raise RuntimeError(
            "Nenhuma cotação encontrada "
            "para os tickers-alvo."
        )

    cot = cot.drop_duplicates(
        [
            "TICKER",
            "DATA",
        ]
    )

    return cot


# ============================================================
# 5. HISTÓRICO POR TICKER
# ============================================================

def _ticker_history(
    cot: pd.DataFrame,
):

    return (
        cot
        .groupby(
            "TICKER",
            as_index=False,
        )
        .agg(
            PRIMEIRA_NEGOCIACAO=(
                "DATA",
                "min",
            ),

            ULTIMA_NEGOCIACAO=(
                "DATA",
                "max",
            ),

            PREGOES_HISTORICOS=(
                "DATA",
                "nunique",
            ),
        )
    )


# ============================================================
# 6. LIQUIDEZ POR TICKER
# ============================================================

def _ticker_liquidity(
    cot: pd.DataFrame,
    liquidity_year: int,
):

    cot_year = cot[
        cot["DATA"]
        .dt.year
        .eq(liquidity_year)
    ].copy()

    daily = (
        cot_year
        .groupby(
            [
                "TICKER",
                "DATA",
            ],
            as_index=False,
        )["VOLTOT"]
        .sum()
    )

    return (
        daily
        .groupby(
            "TICKER",
            as_index=False,
        )
        .agg(
            LIQUIDEZ_MEDIA_DIARIA_2025=(
                "VOLTOT",
                "mean",
            ),

            PREGOES_2025=(
                "DATA",
                "nunique",
            ),
        )
    )


# ============================================================
# 7. INVESTIBILIDADE POR EMPRESA
# ============================================================

def _calculate_investability(
    quality: pd.DataFrame,
    ticker_map: pd.DataFrame,
    hist_ticker: pd.DataFrame,
    liquidity_ticker: pd.DataFrame,
    reference_date,
):

    hist_ticker = hist_ticker.merge(
        liquidity_ticker,
        on="TICKER",
        how="left",
    )

    ticker_empresa = ticker_map.merge(
        hist_ticker,
        on="TICKER",
        how="left",
    )

    historico_empresa = (
        ticker_empresa
        .groupby(
            "CD_CVM",
            as_index=False,
        )
        .agg(
            PRIMEIRA_NEGOCIACAO=(
                "PRIMEIRA_NEGOCIACAO",
                "min",
            ),

            ULTIMA_NEGOCIACAO=(
                "ULTIMA_NEGOCIACAO",
                "max",
            ),

            N_TICKERS_HISTORICOS=(
                "TICKER",
                "nunique",
            ),
        )
    )

    # Para a empresa, utiliza-se a classe/ticker
    # mais líquido no ano analisado.
    liq_empresa = (
        ticker_empresa[
            ticker_empresa[
                "LIQUIDEZ_MEDIA_DIARIA_2025"
            ].notna()
        ]
        .sort_values(
            [
                "CD_CVM",
                "LIQUIDEZ_MEDIA_DIARIA_2025",
            ],
            ascending=[
                True,
                False,
            ],
        )
        .drop_duplicates(
            "CD_CVM"
        )
        [
            [
                "CD_CVM",
                "TICKER",
                "LIQUIDEZ_MEDIA_DIARIA_2025",
                "PREGOES_2025",
            ]
        ]
        .rename(
            columns={
                "TICKER":
                    "TICKER_MAIS_LIQUIDO_2025",
            }
        )
    )

    invest = quality.merge(
        historico_empresa,
        on="CD_CVM",
        how="left",
    )

    invest = invest.merge(
        liq_empresa,
        on="CD_CVM",
        how="left",
    )

    reference_date = pd.Timestamp(
        reference_date
    )

    invest[
        "ANOS_NEGOCIACAO"
    ] = (
        (
            reference_date
            -
            pd.to_datetime(
                invest[
                    "PRIMEIRA_NEGOCIACAO"
                ],
                errors="coerce",
            )
        )
        .dt.days
        /
        365.2425
    )

    invest[
        "PASSA_10_ANOS"
    ] = (
        invest[
            "ANOS_NEGOCIACAO"
        ]
        >= 10
    )

    invest[
        "PASSA_LIQUIDEZ"
    ] = (
        invest[
            "LIQUIDEZ_MEDIA_DIARIA_2025"
        ]
        >= 6_000_000
    )

    invest[
        "APROVADA_INVESTIBILIDADE"
    ] = (
        invest[
            "PASSA_10_ANOS"
        ]
        &
        invest[
            "PASSA_LIQUIDEZ"
        ]
    )

    def motivo19(row):

        motivos = []

        if pd.isna(
            row[
                "PRIMEIRA_NEGOCIACAO"
            ]
        ):

            motivos.append(
                "SEM_HISTORICO_COTAHIST"
            )

        elif not row[
            "PASSA_10_ANOS"
        ]:

            motivos.append(
                "MENOS_DE_10_ANOS"
            )

        if pd.isna(
            row[
                "LIQUIDEZ_MEDIA_DIARIA_2025"
            ]
        ):

            motivos.append(
                "SEM_LIQUIDEZ_2025"
            )

        elif not row[
            "PASSA_LIQUIDEZ"
        ]:

            motivos.append(
                "LIQUIDEZ_MENOR_6M"
            )

        return " | ".join(
            motivos
        )

    invest[
        "MOTIVO_REPROVACAO_B3"
    ] = invest.apply(
        motivo19,
        axis=1,
    )

    return (
        ticker_empresa,
        invest,
    )


# ============================================================
# 8. MOTOR PRINCIPAL
# ============================================================

def run_investability_engine(
    quality: pd.DataFrame,
    fca: pd.DataFrame,
    raw_b3,
    reference_date="2025-12-31",
    liquidity_year=2025,
    first_year=2000,
):

    quality = quality.copy()
    fca = fca.copy()

    quality["CD_CVM"] = pd.to_numeric(
        quality["CD_CVM"],
        errors="coerce",
    )

    if quality[
        "CD_CVM"
    ].duplicated().any():

        raise RuntimeError(
            "Quality possui CD_CVM duplicado."
        )

    if len(quality) != 159:

        raise RuntimeError(
            "Benchmark Cell19 esperado: "
            f"159 empresas. Recebidas: {len(quality)}"
        )

    ticker_map = _build_ticker_map(
        quality,
        fca,
    )

    cot = _load_cotahist(
        Path(raw_b3),
        ticker_map,
        first_year=first_year,
        last_year=liquidity_year,
    )

    hist_ticker = _ticker_history(
        cot
    )

    liquidity_ticker = _ticker_liquidity(
        cot,
        liquidity_year,
    )

    ticker_empresa, invest = (
        _calculate_investability(
            quality,
            ticker_map,
            hist_ticker,
            liquidity_ticker,
            reference_date,
        )
    )

    return {
        "investability": invest,
        "approved": (
            invest[
                invest[
                    "APROVADA_INVESTIBILIDADE"
                ]
            ]
            .sort_values(
                "QUALITY_SCORE",
                ascending=False,
            )
            .reset_index(drop=True)
        ),
        "ticker_history": ticker_empresa,
    }


# ============================================================
# 9. EXPORTAÇÃO
# ============================================================

def save_investability_outputs(
    result,
    output_dir,
):

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    ticker_path = (
        output_dir
        /
        "cell19_b3_ticker_history.csv"
    )

    invest_path = (
        output_dir
        /
        "cell19_b3_investability.csv"
    )

    approved_path = (
        output_dir
        /
        "cell19_b3_investability_approved.csv"
    )

    result[
        "ticker_history"
    ].to_csv(
        ticker_path,
        index=False,
        encoding="utf-8-sig",
    )

    result[
        "investability"
    ].to_csv(
        invest_path,
        index=False,
        encoding="utf-8-sig",
    )

    result[
        "approved"
    ].to_csv(
        approved_path,
        index=False,
        encoding="utf-8-sig",
    )

    return {
        "ticker_history": ticker_path,
        "investability": invest_path,
        "approved": approved_path,
    }
