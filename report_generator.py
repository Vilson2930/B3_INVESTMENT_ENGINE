# ============================================================
# B3_INVESTMENT_ENGINE
# report_generator.py
#
# Gerador do relatório final do sistema.
#
# Não recalcula:
# - Quality
# - Investability
# - Valuation
# - Fundamental Score
# - Indicadores técnicos
#
# Apenas apresenta os resultados produzidos pelo main.py.
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
import json

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

from config import (
    PROJECT_NAME,
    PROJECT_VERSION,
    FINAL_REPORT_DIR,
    validate_config,
)


# ============================================================
# 1. ARQUIVOS
# ============================================================

RESULTS_FILE = (
    FINAL_REPORT_DIR /
    "b3_investment_engine_results.csv"
)

ELIGIBLE_FILE = (
    FINAL_REPORT_DIR /
    "b3_investment_engine_eligible.csv"
)

SUMMARY_FILE = (
    FINAL_REPORT_DIR /
    "run_summary.json"
)

PDF_FILE = (
    FINAL_REPORT_DIR /
    "B3_INVESTMENT_ENGINE_REPORT.pdf"
)


# ============================================================
# 2. FORMATADORES
# ============================================================

def fmt_score(value):

    if pd.isna(value):
        return "-"

    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def fmt_pct(value):

    if pd.isna(value):
        return "-"

    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def fmt_bool(value):

    if pd.isna(value):
        return "-"

    if isinstance(value, str):

        normalized = (
            value
            .strip()
            .lower()
        )

        if normalized in {
            "true",
            "1",
            "yes",
            "sim",
        }:
            return "SIM"

        if normalized in {
            "false",
            "0",
            "no",
            "nao",
            "não",
        }:
            return "NÃO"

    return (
        "SIM"
        if bool(value)
        else "NÃO"
    )


def safe_text(value):

    if pd.isna(value):
        return "-"

    return str(value)


# ============================================================
# 3. CARREGAR RESULTADOS
# ============================================================

def load_results():

    if not RESULTS_FILE.exists():

        raise FileNotFoundError(
            f"Resultado não encontrado: {RESULTS_FILE}"
        )

    results = pd.read_csv(
        RESULTS_FILE,
        low_memory=False,
    )

    if ELIGIBLE_FILE.exists():

        eligible = pd.read_csv(
            ELIGIBLE_FILE,
            low_memory=False,
        )

    else:

        eligible = results.loc[
            results["ELIGIBLE"] == True
        ].copy()

    if SUMMARY_FILE.exists():

        with open(
            SUMMARY_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            summary = json.load(file)

    else:

        summary = {}

    return (
        results,
        eligible,
        summary,
    )


# ============================================================
# 4. RODAPÉ / NUMERAÇÃO
# ============================================================

def add_page_number(
    canvas,
    doc,
):

    canvas.saveState()

    page_number = (
        canvas.getPageNumber()
    )

    text = (
        f"{PROJECT_NAME} | "
        f"Página {page_number}"
    )

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.drawRightString(
        landscape(A4)[0] - 12 * mm,
        8 * mm,
        text,
    )

    canvas.restoreState()


# ============================================================
# 5. ESTILOS
# ============================================================

def build_styles():

    styles = (
        getSampleStyleSheet()
    )

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=10,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=16,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            spaceBefore=8,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SmallText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
        )
    )

    return styles


# ============================================================
# 6. TABELA DE RESUMO
# ============================================================

def build_summary_table(
    results,
    eligible,
    summary,
):

    technical_available = 0

    if (
        not eligible.empty
        and
        "TECHNICAL_AVAILABLE"
        in eligible.columns
    ):

        technical_available = int(
            eligible[
                "TECHNICAL_AVAILABLE"
            ]
            .fillna(False)
            .astype(bool)
            .sum()
        )

    rows = [

        [
            "Indicador",
            "Resultado",
        ],

        [
            "Empresas processadas",
            str(
                summary.get(
                    "companies_processed",
                    len(results),
                )
            ),
        ],

        [
            "Empresas elegíveis",
            str(
                summary.get(
                    "fundamental_eligible",
                    len(eligible),
                )
            ),
        ],

        [
            "Com contexto técnico",
            str(
                summary.get(
                    "technical_context_available",
                    technical_available,
                )
            ),
        ],

        [
            "Ranking",
            "Fundamental Score",
        ],

        [
            "Integração fundamental",
            "70% Quality / 30% Valuation",
        ],

        [
            "Technical Score",
            "NÃO",
        ],

        [
            "Gatilho técnico obrigatório",
            "NÃO",
        ],

        [
            "Técnico participa do ranking",
            "NÃO",
        ],

        [
            "Arquitetura",
            "FUNDAMENTAL FIRST",
        ],
    ]

    table = Table(
        rows,
        colWidths=[
            80 * mm,
            95 * mm,
        ],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor(
                    "#E6E6E6"
                ),
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),

            (
                "FONTNAME",
                (0, 1),
                (0, -1),
                "Helvetica-Bold",
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                8,
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.grey,
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),

            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),

            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
        ])
    )

    return table


# ============================================================
# 7. TABELA DO RANKING
# ============================================================

def build_ranking_table(
    eligible,
):

    headers = [
        "Rank",
        "Ticker",
        "Quality",
        "Valuation",
        "Fundamental",
        "Técnico",
        "Contexto técnico",
    ]

    rows = [
        headers
    ]

    if eligible.empty:

        rows.append([
            "-",
            "Nenhuma empresa elegível",
            "-",
            "-",
            "-",
            "-",
            "-",
        ])

    else:

        ranking = (
            eligible
            .copy()
        )

        if "FUNDAMENTAL_SCORE" in ranking.columns:

            ranking[
                "FUNDAMENTAL_SCORE"
            ] = pd.to_numeric(
                ranking[
                    "FUNDAMENTAL_SCORE"
                ],
                errors="coerce",
            )

            ranking = (
                ranking
                .sort_values(
                    "FUNDAMENTAL_SCORE",
                    ascending=False,
                    na_position="last",
                )
                .reset_index(drop=True)
            )

        for position, row in ranking.iterrows():

            rank = (
                row.get(
                    "FUNDAMENTAL_RANK",
                    position + 1,
                )
            )

            if pd.isna(rank):
                rank = position + 1

            try:
                rank = int(
                    float(rank)
                )
            except (
                TypeError,
                ValueError,
            ):
                rank = (
                    position + 1
                )

            rows.append([

                str(rank),

                safe_text(
                    row.get(
                        "TICKER"
                    )
                ),

                fmt_score(
                    row.get(
                        "QUALITY_SCORE"
                    )
                ),

                fmt_score(
                    row.get(
                        "VALUATION_SCORE"
                    )
                ),

                fmt_score(
                    row.get(
                        "FUNDAMENTAL_SCORE"
                    )
                ),

                fmt_bool(
                    row.get(
                        "TECHNICAL_AVAILABLE"
                    )
                ),

                safe_text(
                    row.get(
                        "TECHNICAL_OBSERVATIONS"
                    )
                ),
            ])

    table = Table(
        rows,
        colWidths=[
            14 * mm,
            20 * mm,
            22 * mm,
            24 * mm,
            25 * mm,
            20 * mm,
            125 * mm,
        ],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor(
                    "#E6E6E6"
                ),
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, 0),
                7,
            ),

            (
                "FONTSIZE",
                (0, 1),
                (-1, -1),
                6.5,
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.grey,
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),

            (
                "ALIGN",
                (0, 1),
                (5, -1),
                "CENTER",
            ),

            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),

            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),
        ])
    )

    return table


# ============================================================
# 8. TABELA TÉCNICA DETALHADA
# ============================================================

def build_technical_table(
    eligible,
):

    headers = [
        "Ticker",
        "Slope SMA200",
        "ATR %",
        "ROC 60",
        "MACD Hist %",
        "Dist. SMA200",
        "BB Width",
        "Dist. SMA50",
    ]

    rows = [
        headers
    ]

    if eligible.empty:

        rows.append(
            [
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
            ]
        )

    else:

        ranking = (
            eligible
            .copy()
        )

        if "FUNDAMENTAL_SCORE" in ranking.columns:

            ranking = (
                ranking
                .sort_values(
                    "FUNDAMENTAL_SCORE",
                    ascending=False,
                    na_position="last",
                )
            )

        for _, row in ranking.iterrows():

            rows.append([

                safe_text(
                    row.get(
                        "TICKER"
                    )
                ),

                fmt_pct(
                    row.get(
                        "SMA200_SLOPE_20D"
                    )
                ),

                fmt_pct(
                    row.get(
                        "ATR_PCT"
                    )
                ),

                fmt_pct(
                    row.get(
                        "ROC_60"
                    )
                ),

                fmt_pct(
                    row.get(
                        "MACD_HIST_PCT"
                    )
                ),

                fmt_pct(
                    row.get(
                        "DIST_SMA_200"
                    )
                ),

                fmt_pct(
                    row.get(
                        "BB_WIDTH"
                    )
                ),

                fmt_pct(
                    row.get(
                        "DIST_SMA_50"
                    )
                ),
            ])

    table = Table(
        rows,
        colWidths=[
            28 * mm,
            31 * mm,
            27 * mm,
            27 * mm,
            31 * mm,
            31 * mm,
            28 * mm,
            31 * mm,
        ],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor(
                    "#E6E6E6"
                ),
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7,
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.grey,
            ),

            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "CENTER",
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),
        ])
    )

    return table


# ============================================================
# 9. GERAR PDF
# ============================================================

def generate_report():

    validate_config()

    (
        results,
        eligible,
        summary,
    ) = load_results()

    FINAL_REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    styles = build_styles()

    document = SimpleDocTemplate(

        str(PDF_FILE),

        pagesize=landscape(A4),

        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,

        title=(
            "B3 Investment Engine Report"
        ),

        author=PROJECT_NAME,
    )

    story = []

    # ========================================================
    # CAPA
    # ========================================================

    story.append(
        Spacer(
            1,
            12 * mm,
        )
    )

    story.append(
        Paragraph(
            "B3 INVESTMENT ENGINE",
            styles["ReportTitle"],
        )
    )

    story.append(
        Paragraph(
            (
                "Relatório Integrado — "
                "Fundamental Engine + "
                "Technical Timing Engine"
            ),
            styles[
                "ReportSubtitle"
            ],
        )
    )

    generated_at = (
        datetime.now(
            timezone.utc
        )
        .strftime(
            "%d/%m/%Y %H:%M UTC"
        )
    )

    story.append(
        Paragraph(
            (
                f"Versão {PROJECT_VERSION}"
                f"<br/>Gerado em {generated_at}"
            ),
            styles[
                "ReportSubtitle"
            ],
        )
    )

    story.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    story.append(
        Paragraph(
            "Arquitetura",
            styles[
                "SectionTitle"
            ],
        )
    )

    story.append(
        Paragraph(
            (
                "<b>FUNDAMENTAL FIRST</b><br/><br/>"
                "Quality → Investability → Valuation → "
                "Technical Timing → Integration → Final Report"
            ),
            styles[
                "SmallText"
            ],
        )
    )

    story.append(
        Spacer(
            1,
            6 * mm,
        )
    )

    story.append(
        Paragraph(
            (
                "A análise técnica é apresentada como "
                "contexto de timing. Ela não modifica "
                "Quality, Valuation ou Fundamental Score "
                "e não funciona como gatilho obrigatório."
            ),
            styles[
                "SmallText"
            ],
        )
    )

    story.append(
        PageBreak()
    )

    # ========================================================
    # RESUMO
    # ========================================================

    story.append(
        Paragraph(
            "Resumo da execução",
            styles[
                "SectionTitle"
            ],
        )
    )

    story.append(
        build_summary_table(
            results,
            eligible,
            summary,
        )
    )

    story.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    story.append(
        Paragraph(
            (
                "O ranking apresentado abaixo é "
                "exclusivamente fundamental. "
                "Os indicadores técnicos não alteram "
                "a posição das empresas no ranking."
            ),
            styles[
                "SmallText"
            ],
        )
    )

    story.append(
        PageBreak()
    )

    # ========================================================
    # RANKING
    # ========================================================

    story.append(
        Paragraph(
            "Ranking Fundamental",
            styles[
                "SectionTitle"
            ],
        )
    )

    story.append(
        build_ranking_table(
            eligible
        )
    )

    story.append(
        PageBreak()
    )

    # ========================================================
    # CONTEXTO TÉCNICO
    # ========================================================

    story.append(
        Paragraph(
            "Contexto Técnico",
            styles[
                "SectionTitle"
            ],
        )
    )

    story.append(
        Paragraph(
            (
                "Indicadores preservados pelo estudo técnico. "
                "Os valores são informativos e não constituem "
                "Technical Score nem gatilho obrigatório."
            ),
            styles[
                "SmallText"
            ],
        )
    )

    story.append(
        Spacer(
            1,
            5 * mm,
        )
    )

    story.append(
        build_technical_table(
            eligible
        )
    )

    # ========================================================
    # GERAR
    # ========================================================

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    print("=" * 80)
    print(PROJECT_NAME)
    print("FINAL REPORT")
    print("=" * 80)

    print(
        f"Empresas processadas: "
        f"{len(results)}"
    )

    print(
        f"Empresas elegíveis: "
        f"{len(eligible)}"
    )

    print(
        "\n✓ Ranking fundamental preservado."
    )

    print(
        "✓ Contexto técnico preservado."
    )

    print(
        "✓ Nenhum Technical Score criado."
    )

    print(
        "✓ Nenhum gatilho técnico obrigatório criado."
    )

    print(
        "\nPDF:"
    )

    print(
        PDF_FILE
    )

    print("=" * 80)

    return PDF_FILE


# ============================================================
# 10. EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    generate_report()
