# ============================================================
# B3_INVESTMENT_ENGINE
# fundamental_engine.py
#
# Orquestrador do Motor Fundamentalista
#
# Fluxo:
# Quality
#   ↓
# Investability
#   ↓
# Valuation
#   ↓
# Fundamental Ranking
# ============================================================

from dataclasses import dataclass
from typing import Optional

from config import (
    PROJECT_NAME,
    QUALITY_MIN_SCORE,
    MIN_HISTORY_YEARS,
    MIN_AVG_DAILY_LIQUIDITY_BRL,
    QUALITY_WEIGHT,
    VALUATION_WEIGHT,
    validate_config,
)


# ============================================================
# 1. ESTRUTURA DE ENTRADA
# ============================================================

@dataclass
class FundamentalInput:

    ticker: str

    quality_score: Optional[float]

    history_years: Optional[float]

    avg_daily_liquidity_brl: Optional[float]

    valuation_score: Optional[float]


# ============================================================
# 2. ESTRUTURA DE SAÍDA
# ============================================================

@dataclass
class FundamentalResult:

    ticker: str

    quality_score: Optional[float]

    quality_approved: bool

    history_years: Optional[float]

    history_approved: bool

    avg_daily_liquidity_brl: Optional[float]

    liquidity_approved: bool

    investability_approved: bool

    valuation_score: Optional[float]

    valuation_available: bool

    fundamental_score: Optional[float]

    fundamental_approved: bool

    status: str

    rejection_reason: Optional[str]


# ============================================================
# 3. FUNÇÕES AUXILIARES
# ============================================================

def _valid_number(value) -> bool:

    if value is None:
        return False

    try:
        value = float(value)
    except (TypeError, ValueError):
        return False

    return value == value


def _score_in_range(value) -> bool:

    if not _valid_number(value):
        return False

    value = float(value)

    return 0.0 <= value <= 100.0


# ============================================================
# 4. QUALITY GATE
# ============================================================

def evaluate_quality(
    quality_score: Optional[float]
) -> bool:

    if not _score_in_range(quality_score):
        return False

    return (
        float(quality_score)
        >= QUALITY_MIN_SCORE
    )


# ============================================================
# 5. HISTÓRICO MÍNIMO
# ============================================================

def evaluate_history(
    history_years: Optional[float]
) -> bool:

    if not _valid_number(history_years):
        return False

    return (
        float(history_years)
        >= MIN_HISTORY_YEARS
    )


# ============================================================
# 6. LIQUIDEZ
# ============================================================

def evaluate_liquidity(
    avg_daily_liquidity_brl: Optional[float]
) -> bool:

    if not _valid_number(
        avg_daily_liquidity_brl
    ):
        return False

    return (
        float(avg_daily_liquidity_brl)
        >= MIN_AVG_DAILY_LIQUIDITY_BRL
    )


# ============================================================
# 7. INVESTABILIDADE
# ============================================================

def evaluate_investability(
    history_years: Optional[float],
    avg_daily_liquidity_brl: Optional[float],
) -> tuple[bool, bool, bool]:

    history_approved = evaluate_history(
        history_years
    )

    liquidity_approved = evaluate_liquidity(
        avg_daily_liquidity_brl
    )

    investability_approved = (
        history_approved
        and liquidity_approved
    )

    return (
        history_approved,
        liquidity_approved,
        investability_approved,
    )


# ============================================================
# 8. VALUATION
# ============================================================

def evaluate_valuation(
    valuation_score: Optional[float]
) -> bool:

    return _score_in_range(
        valuation_score
    )


# ============================================================
# 9. SCORE FUNDAMENTAL FINAL
# ============================================================

def calculate_fundamental_score(
    quality_score: float,
    valuation_score: float,
) -> float:

    if not _score_in_range(quality_score):

        raise ValueError(
            "QUALITY_SCORE inválido."
        )

    if not _score_in_range(valuation_score):

        raise ValueError(
            "VALUATION_SCORE inválido."
        )

    score = (
        float(quality_score)
        * QUALITY_WEIGHT
        +
        float(valuation_score)
        * VALUATION_WEIGHT
    )

    return round(
        score,
        4
    )


# ============================================================
# 10. MOTOR FUNDAMENTALISTA
# ============================================================

def evaluate_company(
    data: FundamentalInput
) -> FundamentalResult:

    ticker = str(
        data.ticker
    ).strip().upper()

    if not ticker:

        raise ValueError(
            "Ticker vazio."
        )

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    quality_approved = evaluate_quality(
        data.quality_score
    )

    # --------------------------------------------------------
    # INVESTABILITY
    # --------------------------------------------------------

    (
        history_approved,
        liquidity_approved,
        investability_approved,
    ) = evaluate_investability(
        data.history_years,
        data.avg_daily_liquidity_brl,
    )

    # --------------------------------------------------------
    # VALUATION
    # --------------------------------------------------------

    valuation_available = evaluate_valuation(
        data.valuation_score
    )

    # --------------------------------------------------------
    # HARD GATES
    # --------------------------------------------------------

    if not quality_approved:

        return FundamentalResult(

            ticker=ticker,

            quality_score=data.quality_score,

            quality_approved=False,

            history_years=data.history_years,

            history_approved=history_approved,

            avg_daily_liquidity_brl=(
                data.avg_daily_liquidity_brl
            ),

            liquidity_approved=(
                liquidity_approved
            ),

            investability_approved=(
                investability_approved
            ),

            valuation_score=(
                data.valuation_score
            ),

            valuation_available=(
                valuation_available
            ),

            fundamental_score=None,

            fundamental_approved=False,

            status="INELEGIVEL",

            rejection_reason=(
                "QUALITY_GATE_FAILED"
            ),
        )

    if not history_approved:

        return FundamentalResult(

            ticker=ticker,

            quality_score=data.quality_score,

            quality_approved=True,

            history_years=data.history_years,

            history_approved=False,

            avg_daily_liquidity_brl=(
                data.avg_daily_liquidity_brl
            ),

            liquidity_approved=(
                liquidity_approved
            ),

            investability_approved=False,

            valuation_score=(
                data.valuation_score
            ),

            valuation_available=(
                valuation_available
            ),

            fundamental_score=None,

            fundamental_approved=False,

            status="INELEGIVEL",

            rejection_reason=(
                "MIN_HISTORY_FAILED"
            ),
        )

    if not liquidity_approved:

        return FundamentalResult(

            ticker=ticker,

            quality_score=data.quality_score,

            quality_approved=True,

            history_years=data.history_years,

            history_approved=True,

            avg_daily_liquidity_brl=(
                data.avg_daily_liquidity_brl
            ),

            liquidity_approved=False,

            investability_approved=False,

            valuation_score=(
                data.valuation_score
            ),

            valuation_available=(
                valuation_available
            ),

            fundamental_score=None,

            fundamental_approved=False,

            status="INELEGIVEL",

            rejection_reason=(
                "MIN_LIQUIDITY_FAILED"
            ),
        )

    # --------------------------------------------------------
    # VALUATION PENDENTE
    # --------------------------------------------------------

    if not valuation_available:

        return FundamentalResult(

            ticker=ticker,

            quality_score=data.quality_score,

            quality_approved=True,

            history_years=data.history_years,

            history_approved=True,

            avg_daily_liquidity_brl=(
                data.avg_daily_liquidity_brl
            ),

            liquidity_approved=True,

            investability_approved=True,

            valuation_score=None,

            valuation_available=False,

            fundamental_score=None,

            fundamental_approved=False,

            status="AGUARDANDO_VALUATION",

            rejection_reason=None,
        )

    # --------------------------------------------------------
    # INTEGRAÇÃO 70 / 30
    # --------------------------------------------------------

    fundamental_score = (
        calculate_fundamental_score(
            quality_score=float(
                data.quality_score
            ),
            valuation_score=float(
                data.valuation_score
            ),
        )
    )

    # --------------------------------------------------------
    # APROVAÇÃO FUNDAMENTAL
    # --------------------------------------------------------
    #
    # IMPORTANTE:
    #
    # Não criamos um segundo corte arbitrário sobre o score
    # 70/30.
    #
    # Quality + Investability são os gates.
    # Valuation participa do ranking.
    # --------------------------------------------------------

    fundamental_approved = True

    return FundamentalResult(

        ticker=ticker,

        quality_score=float(
            data.quality_score
        ),

        quality_approved=True,

        history_years=float(
            data.history_years
        ),

        history_approved=True,

        avg_daily_liquidity_brl=float(
            data.avg_daily_liquidity_brl
        ),

        liquidity_approved=True,

        investability_approved=True,

        valuation_score=float(
            data.valuation_score
        ),

        valuation_available=True,

        fundamental_score=(
            fundamental_score
        ),

        fundamental_approved=(
            fundamental_approved
        ),

        status="ELEGIVEL",

        rejection_reason=None,
    )


# ============================================================
# 11. CONVERSÃO PARA DICIONÁRIO
# ============================================================

def result_to_dict(
    result: FundamentalResult
) -> dict:

    return {
        "TICKER":
            result.ticker,

        "QUALITY_SCORE":
            result.quality_score,

        "QUALITY_APPROVED":
            result.quality_approved,

        "HISTORY_YEARS":
            result.history_years,

        "HISTORY_APPROVED":
            result.history_approved,

        "AVG_DAILY_LIQUIDITY_BRL":
            result.avg_daily_liquidity_brl,

        "LIQUIDITY_APPROVED":
            result.liquidity_approved,

        "INVESTABILITY_APPROVED":
            result.investability_approved,

        "VALUATION_SCORE":
            result.valuation_score,

        "VALUATION_AVAILABLE":
            result.valuation_available,

        "FUNDAMENTAL_SCORE":
            result.fundamental_score,

        "FUNDAMENTAL_APPROVED":
            result.fundamental_approved,

        "STATUS":
            result.status,

        "REJECTION_REASON":
            result.rejection_reason,
    }


# ============================================================
# 12. AUTOTESTE
# ============================================================

def self_test():

    # --------------------------------------------------------
    # Caso 1:
    # Empresa completamente elegível
    # --------------------------------------------------------

    approved = evaluate_company(

        FundamentalInput(

            ticker="TEST3",

            quality_score=80.0,

            history_years=15.0,

            avg_daily_liquidity_brl=(
                20_000_000.0
            ),

            valuation_score=70.0,
        )
    )

    assert approved.quality_approved
    assert approved.investability_approved
    assert approved.valuation_available
    assert approved.fundamental_approved

    assert (
        approved.fundamental_score
        ==
        77.0
    )

    # --------------------------------------------------------
    # Caso 2:
    # Quality reprovado
    # --------------------------------------------------------

    rejected_quality = evaluate_company(

        FundamentalInput(

            ticker="TEST4",

            quality_score=50.0,

            history_years=20.0,

            avg_daily_liquidity_brl=(
                50_000_000.0
            ),

            valuation_score=95.0,
        )
    )

    assert not (
        rejected_quality.fundamental_approved
    )

    assert (
        rejected_quality.rejection_reason
        ==
        "QUALITY_GATE_FAILED"
    )

    # --------------------------------------------------------
    # Caso 3:
    # Sem 10 anos
    # --------------------------------------------------------

    rejected_history = evaluate_company(

        FundamentalInput(

            ticker="TEST5",

            quality_score=90.0,

            history_years=5.0,

            avg_daily_liquidity_brl=(
                50_000_000.0
            ),

            valuation_score=90.0,
        )
    )

    assert not (
        rejected_history.fundamental_approved
    )

    assert (
        rejected_history.rejection_reason
        ==
        "MIN_HISTORY_FAILED"
    )

    # --------------------------------------------------------
    # Caso 4:
    # Liquidez insuficiente
    # --------------------------------------------------------

    rejected_liquidity = evaluate_company(

        FundamentalInput(

            ticker="TEST6",

            quality_score=90.0,

            history_years=20.0,

            avg_daily_liquidity_brl=(
                1_000_000.0
            ),

            valuation_score=90.0,
        )
    )

    assert not (
        rejected_liquidity.fundamental_approved
    )

    assert (
        rejected_liquidity.rejection_reason
        ==
        "MIN_LIQUIDITY_FAILED"
    )

    # --------------------------------------------------------
    # Caso 5:
    # Valuation ainda indisponível
    # --------------------------------------------------------

    pending = evaluate_company(

        FundamentalInput(

            ticker="TEST7",

            quality_score=90.0,

            history_years=20.0,

            avg_daily_liquidity_brl=(
                50_000_000.0
            ),

            valuation_score=None,
        )
    )

    assert pending.investability_approved
    assert not pending.valuation_available

    assert (
        pending.status
        ==
        "AGUARDANDO_VALUATION"
    )

    print(
        "✓ Fundamental Engine: autoteste aprovado."
    )


# ============================================================
# 13. EXECUÇÃO DIRETA
# ============================================================

if __name__ == "__main__":

    validate_config()

    print("=" * 72)
    print(PROJECT_NAME)
    print("FUNDAMENTAL ENGINE")
    print("=" * 72)

    self_test()

    print(
        "✓ Quality Gate preservado."
    )

    print(
        "✓ Investability Gate preservado."
    )

    print(
        "✓ Valuation preservado."
    )

    print(
        "✓ Ranking 70% Quality / "
        "30% Valuation preservado."
    )

    print(
        "✓ Nenhuma regra técnica "
        "foi inserida no Fundamental Engine."
    )
