# ============================================================
# B3_INVESTMENT_ENGINE
# integration_engine.py
#
# Integração oficial:
#
# Fundamental Engine
#        ↓
# Technical Timing Engine
#        ↓
# Resultado Integrado
#
# REGRA CENTRAL:
# O técnico fornece CONTEXTO.
# Não altera Quality, Valuation ou Fundamental Score.
# ============================================================

from dataclasses import dataclass, asdict
from typing import Optional

from config import (
    PROJECT_NAME,
    FUNDAMENTAL_FIRST,
    TECHNICAL_MANDATORY_TRIGGER,
    TECHNICAL_CAN_VETO_FUNDAMENTAL,
    TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL,
    TECHNICAL_SCORE_ENABLED,
    validate_config,
)

from fundamental_engine import (
    FundamentalResult,
)

from technical_engine import (
    TechnicalResult,
)


# ============================================================
# 1. RESULTADO INTEGRADO
# ============================================================

@dataclass
class IntegratedResult:

    ticker: str

    # --------------------------------------------------------
    # FUNDAMENTAL
    # --------------------------------------------------------

    quality_score: Optional[float]

    quality_approved: bool

    investability_approved: bool

    valuation_score: Optional[float]

    valuation_available: bool

    fundamental_score: Optional[float]

    fundamental_approved: bool

    fundamental_status: str

    rejection_reason: Optional[str]

    # --------------------------------------------------------
    # TÉCNICO
    # --------------------------------------------------------

    technical_available: bool

    technical_role: str

    technical_score: Optional[float]

    mandatory_trigger: bool

    validated_oos_trigger: bool

    sma200_slope_20d: Optional[float]

    atr_pct: Optional[float]

    roc_60: Optional[float]

    macd_hist_pct: Optional[float]

    dist_sma_200: Optional[float]

    bb_width: Optional[float]

    dist_sma_50: Optional[float]

    technical_observations: str

    # --------------------------------------------------------
    # DECISÃO INTEGRADA
    # --------------------------------------------------------

    eligible: bool

    integration_status: str

    technical_context_status: str


# ============================================================
# 2. VALIDAR CONSISTÊNCIA ENTRE MOTORES
# ============================================================

def validate_engine_consistency(
    fundamental: FundamentalResult,
    technical: TechnicalResult,
):

    fundamental_ticker = str(
        fundamental.ticker
    ).strip().upper()

    technical_ticker = str(
        technical.ticker
    ).strip().upper()

    if (
        fundamental_ticker
        != technical_ticker
    ):

        raise ValueError(
            "Ticker do Fundamental Engine "
            "difere do Technical Engine: "
            f"{fundamental_ticker} != "
            f"{technical_ticker}"
        )

    # --------------------------------------------------------
    # REGRA DE SEGURANÇA
    # --------------------------------------------------------
    #
    # Empresa fundamentalmente reprovada não pode aparecer
    # com gatilho técnico obrigatório.
    # --------------------------------------------------------

    if (
        not fundamental.fundamental_approved
        and technical.mandatory_trigger
    ):

        raise RuntimeError(
            "Violação metodológica: empresa fundamentalmente "
            "reprovada recebeu gatilho técnico obrigatório."
        )

    # --------------------------------------------------------
    # NÃO EXISTE TECHNICAL SCORE
    # --------------------------------------------------------

    if technical.technical_score is not None:

        raise RuntimeError(
            "Violação metodológica: Technical Score "
            "não foi autorizado pela arquitetura FINAL_V1."
        )

    # --------------------------------------------------------
    # NENHUM GATILHO OOS VALIDADO
    # --------------------------------------------------------

    if technical.validated_oos_trigger:

        raise RuntimeError(
            "Violação metodológica: nenhum gatilho técnico "
            "obrigatório sobreviveu à validação OOS."
        )

    return True


# ============================================================
# 3. DEFINIR STATUS DO CONTEXTO TÉCNICO
# ============================================================

def get_technical_context_status(
    fundamental: FundamentalResult,
    technical: TechnicalResult,
) -> str:

    if not fundamental.fundamental_approved:

        return "NAO_APLICAVEL"

    if technical.technical_available:

        return "DISPONIVEL"

    return "INDISPONIVEL"


# ============================================================
# 4. DEFINIR STATUS INTEGRADO
# ============================================================

def get_integration_status(
    fundamental: FundamentalResult,
    technical: TechnicalResult,
) -> str:

    # --------------------------------------------------------
    # QUALITY / INVESTABILITY REPROVADOS
    # --------------------------------------------------------

    if (
        fundamental.status
        ==
        "INELEGIVEL"
    ):

        return "INELEGIVEL_FUNDAMENTAL"

    # --------------------------------------------------------
    # VALUATION PENDENTE
    # --------------------------------------------------------

    if (
        fundamental.status
        ==
        "AGUARDANDO_VALUATION"
    ):

        return "AGUARDANDO_VALUATION"

    # --------------------------------------------------------
    # FUNDAMENTAL APROVADO
    # --------------------------------------------------------

    if fundamental.fundamental_approved:

        if technical.technical_available:

            return (
                "ELEGIVEL_COM_CONTEXTO_TECNICO"
            )

        return (
            "ELEGIVEL_SEM_CONTEXTO_TECNICO"
        )

    return "STATUS_INDETERMINADO"


# ============================================================
# 5. INTEGRAÇÃO PRINCIPAL
# ============================================================

def integrate(
    fundamental: FundamentalResult,
    technical: TechnicalResult,
) -> IntegratedResult:

    # --------------------------------------------------------
    # VALIDAR CONFIGURAÇÃO
    # --------------------------------------------------------

    validate_config()

    # --------------------------------------------------------
    # VALIDAR MOTORES
    # --------------------------------------------------------

    validate_engine_consistency(
        fundamental,
        technical,
    )

    ticker = str(
        fundamental.ticker
    ).strip().upper()

    # --------------------------------------------------------
    # ELEGIBILIDADE
    # --------------------------------------------------------
    #
    # FUNDAMENTAL FIRST:
    #
    # O resultado técnico NÃO participa desta expressão.
    # --------------------------------------------------------

    eligible = bool(
        fundamental.fundamental_approved
    )

    # --------------------------------------------------------
    # PROTEÇÃO EXPLÍCITA
    # --------------------------------------------------------

    if (
        not fundamental.fundamental_approved
        and eligible
    ):

        raise RuntimeError(
            "Technical Engine tentou recuperar "
            "empresa fundamentalmente reprovada."
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    integration_status = (
        get_integration_status(
            fundamental,
            technical,
        )
    )

    technical_context_status = (
        get_technical_context_status(
            fundamental,
            technical,
        )
    )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return IntegratedResult(

        ticker=ticker,

        # FUNDAMENTAL
        quality_score=(
            fundamental.quality_score
        ),

        quality_approved=(
            fundamental.quality_approved
        ),

        investability_approved=(
            fundamental.investability_approved
        ),

        valuation_score=(
            fundamental.valuation_score
        ),

        valuation_available=(
            fundamental.valuation_available
        ),

        fundamental_score=(
            fundamental.fundamental_score
        ),

        fundamental_approved=(
            fundamental.fundamental_approved
        ),

        fundamental_status=(
            fundamental.status
        ),

        rejection_reason=(
            fundamental.rejection_reason
        ),

        # TÉCNICO
        technical_available=(
            technical.technical_available
        ),

        technical_role=(
            technical.technical_role
        ),

        technical_score=(
            technical.technical_score
        ),

        mandatory_trigger=(
            technical.mandatory_trigger
        ),

        validated_oos_trigger=(
            technical.validated_oos_trigger
        ),

        sma200_slope_20d=(
            technical.sma200_slope_20d
        ),

        atr_pct=(
            technical.atr_pct
        ),

        roc_60=(
            technical.roc_60
        ),

        macd_hist_pct=(
            technical.macd_hist_pct
        ),

        dist_sma_200=(
            technical.dist_sma_200
        ),

        bb_width=(
            technical.bb_width
        ),

        dist_sma_50=(
            technical.dist_sma_50
        ),

        technical_observations=(
            technical.observations
        ),

        # INTEGRAÇÃO
        eligible=eligible,

        integration_status=(
            integration_status
        ),

        technical_context_status=(
            technical_context_status
        ),
    )


# ============================================================
# 6. CONVERTER RESULTADO PARA DICIONÁRIO
# ============================================================

def result_to_dict(
    result: IntegratedResult
) -> dict:

    raw = asdict(
        result
    )

    return {
        key.upper(): value
        for key, value in raw.items()
    }


# ============================================================
# 7. AUTOTESTE
# ============================================================

def self_test():

    # --------------------------------------------------------
    # CASO 1
    # Fundamental aprovado + técnico disponível
    # --------------------------------------------------------

    fundamental_ok = FundamentalResult(

        ticker="TEST3",

        quality_score=85.0,

        quality_approved=True,

        history_years=15.0,

        history_approved=True,

        avg_daily_liquidity_brl=(
            20_000_000.0
        ),

        liquidity_approved=True,

        investability_approved=True,

        valuation_score=75.0,

        valuation_available=True,

        fundamental_score=82.0,

        fundamental_approved=True,

        status="ELEGIVEL",

        rejection_reason=None,
    )

    technical_ok = TechnicalResult(

        ticker="TEST3",

        technical_available=True,

        technical_role="ENTRY_CONTEXT",

        technical_engine_version="FINAL_V1",

        technical_engine_mode=(
            "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT"
        ),

        technical_score=None,

        mandatory_trigger=False,

        validated_oos_trigger=False,

        sma200_slope_20d=0.05,

        atr_pct=0.03,

        roc_60=-0.04,

        macd_hist_pct=0.002,

        dist_sma_200=0.10,

        bb_width=0.15,

        dist_sma_50=-0.02,

        observations=(
            "SMA200_INCLINACAO_POSITIVA|"
            "ROC60_NEGATIVO"
        ),
    )

    result_ok = integrate(
        fundamental_ok,
        technical_ok,
    )

    assert result_ok.eligible is True

    assert (
        result_ok.integration_status
        ==
        "ELEGIVEL_COM_CONTEXTO_TECNICO"
    )

    assert (
        result_ok.technical_score
        is None
    )

    # --------------------------------------------------------
    # CASO 2
    # Fundamental reprovado
    # --------------------------------------------------------

    fundamental_bad = FundamentalResult(

        ticker="TEST4",

        quality_score=50.0,

        quality_approved=False,

        history_years=15.0,

        history_approved=True,

        avg_daily_liquidity_brl=(
            20_000_000.0
        ),

        liquidity_approved=True,

        investability_approved=True,

        valuation_score=90.0,

        valuation_available=True,

        fundamental_score=None,

        fundamental_approved=False,

        status="INELEGIVEL",

        rejection_reason=(
            "QUALITY_GATE_FAILED"
        ),
    )

    technical_bad = TechnicalResult(

        ticker="TEST4",

        technical_available=False,

        technical_role="NOT_APPLICABLE",

        technical_engine_version="FINAL_V1",

        technical_engine_mode=(
            "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT"
        ),

        technical_score=None,

        mandatory_trigger=False,

        validated_oos_trigger=False,

        sma200_slope_20d=None,

        atr_pct=None,

        roc_60=None,

        macd_hist_pct=None,

        dist_sma_200=None,

        bb_width=None,

        dist_sma_50=None,

        observations=(
            "FUNDAMENTAL_NOT_APPROVED"
        ),
    )

    result_bad = integrate(
        fundamental_bad,
        technical_bad,
    )

    assert (
        result_bad.eligible
        is False
    )

    assert (
        result_bad.integration_status
        ==
        "INELEGIVEL_FUNDAMENTAL"
    )

    assert (
        result_bad.technical_context_status
        ==
        "NAO_APLICAVEL"
    )

    # --------------------------------------------------------
    # CASO 3
    # Fundamental aprovado + técnico indisponível
    # --------------------------------------------------------

    technical_missing = TechnicalResult(

        ticker="TEST3",

        technical_available=False,

        technical_role="ENTRY_CONTEXT",

        technical_engine_version="FINAL_V1",

        technical_engine_mode=(
            "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT"
        ),

        technical_score=None,

        mandatory_trigger=False,

        validated_oos_trigger=False,

        sma200_slope_20d=None,

        atr_pct=None,

        roc_60=None,

        macd_hist_pct=None,

        dist_sma_200=None,

        bb_width=None,

        dist_sma_50=None,

        observations=(
            "SEM_CONTEXTO_TECNICO"
        ),
    )

    result_missing = integrate(
        fundamental_ok,
        technical_missing,
    )

    assert (
        result_missing.eligible
        is True
    )

    assert (
        result_missing.integration_status
        ==
        "ELEGIVEL_SEM_CONTEXTO_TECNICO"
    )

    # --------------------------------------------------------
    # REGRAS CONGELADAS
    # --------------------------------------------------------

    assert FUNDAMENTAL_FIRST is True

    assert (
        TECHNICAL_MANDATORY_TRIGGER
        is False
    )

    assert (
        TECHNICAL_CAN_VETO_FUNDAMENTAL
        is False
    )

    assert (
        TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL
        is False
    )

    assert (
        TECHNICAL_SCORE_ENABLED
        is False
    )

    print(
        "✓ Integration Engine: "
        "autoteste aprovado."
    )


# ============================================================
# 8. EXECUÇÃO DIRETA
# ============================================================

if __name__ == "__main__":

    validate_config()

    print("=" * 72)
    print(PROJECT_NAME)
    print("INTEGRATION ENGINE")
    print("=" * 72)

    self_test()

    print(
        "✓ Fundamental Engine mantém "
        "a elegibilidade."
    )

    print(
        "✓ Technical Timing Engine "
        "fornece contexto."
    )

    print(
        "✓ Technical Score não existe."
    )

    print(
        "✓ Técnico não altera Quality."
    )

    print(
        "✓ Técnico não altera Valuation."
    )

    print(
        "✓ Técnico não altera "
        "Fundamental Score."
    )

    print(
        "✓ Técnico não recupera "
        "empresa reprovada."
    )

    print(
        "✓ Integração FUNDAMENTAL FIRST "
        "preservada."
    )
