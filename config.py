# ============================================================
# B3_INVESTMENT_ENGINE
# config.py
# Configuração central do sistema
# ============================================================

from pathlib import Path


# ============================================================
# 1. IDENTIFICAÇÃO
# ============================================================

PROJECT_NAME = "B3_INVESTMENT_ENGINE"
PROJECT_VERSION = "1.0.0"

ARCHITECTURE = "FUNDAMENTAL_FIRST"


# ============================================================
# 2. DIRETÓRIOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
CHECKPOINTS_DIR = BASE_DIR / "checkpoints"
LOGS_DIR = BASE_DIR / "logs"

FUNDAMENTAL_DIR = BASE_DIR / "fundamental_engine"
QUALITY_DIR = FUNDAMENTAL_DIR / "quality"
INVESTABILITY_DIR = FUNDAMENTAL_DIR / "investability"
VALUATION_DIR = FUNDAMENTAL_DIR / "valuation"

TECHNICAL_DIR = BASE_DIR / "technical_timing_engine"
INTEGRATION_DIR = BASE_DIR / "integration_engine"
FINAL_REPORT_DIR = BASE_DIR / "final_report"


# ============================================================
# 3. CRIAR DIRETÓRIOS OPERACIONAIS
# ============================================================

for directory in [
    DATA_DIR,
    CHECKPOINTS_DIR,
    LOGS_DIR,
    QUALITY_DIR,
    INVESTABILITY_DIR,
    VALUATION_DIR,
    TECHNICAL_DIR,
    INTEGRATION_DIR,
    FINAL_REPORT_DIR,
]:
    directory.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# 4. PRINCÍPIOS FUNDAMENTAIS
# ============================================================

FUNDAMENTAL_FIRST = True

QUALITY_IS_GATE = True

INVESTABILITY_REQUIRED = True

VALUATION_AFTER_QUALITY = True

TECHNICAL_AFTER_FUNDAMENTAL = True


# ============================================================
# 5. QUALITY ENGINE
# ============================================================

# Gate mínimo congelado na arquitetura fundamental.

QUALITY_MIN_SCORE = 60.0

# Empresa reprovada no Quality Engine permanece inelegível.

QUALITY_FAILED_IS_INELIGIBLE = True


# ============================================================
# 6. INVESTABILITY ENGINE
# ============================================================

# Histórico mínimo de negociação/listagem.

MIN_HISTORY_YEARS = 10

# Liquidez média diária mínima utilizada no estudo.

MIN_AVG_DAILY_LIQUIDITY_BRL = 6_000_000.0


# ============================================================
# 7. FUNDAMENTAL RANKING
# ============================================================

# Integração congelada:
#
# 70% Quality
# 30% Valuation

QUALITY_WEIGHT = 0.70
VALUATION_WEIGHT = 0.30

assert abs(
    QUALITY_WEIGHT +
    VALUATION_WEIGHT -
    1.0
) < 1e-12


# ============================================================
# 8. TECHNICAL TIMING ENGINE
# ============================================================

TECHNICAL_ENGINE_VERSION = "FINAL_V1"

TECHNICAL_ENGINE_MODE = (
    "FUNDAMENTAL_FIRST_TECHNICAL_CONTEXT"
)

# Resultado final do estudo walk-forward/OOS:
# nenhum dos pares candidatos foi aprovado como
# gatilho técnico obrigatório.

OOS_VALIDATED_MANDATORY_PAIRS = 0

TECHNICAL_MANDATORY_TRIGGER = False

TECHNICAL_CAN_VETO_FUNDAMENTAL = False

TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL = False

TECHNICAL_SCORE_ENABLED = False


# ============================================================
# 9. INDICADORES TÉCNICOS PRESERVADOS
# ============================================================
#
# Estes indicadores permanecem disponíveis como contexto.
# Não formam score técnico e não são gatilhos obrigatórios.
# ============================================================

TECHNICAL_CONTEXT_INDICATORS = [

    "SMA200_SLOPE_20D",

    "ATR_PCT",

    "ROC_60",

    "MACD_HIST_PCT",

    "DIST_SMA_200",

    "BB_WIDTH",

    "DIST_SMA_50",
]


# ============================================================
# 10. HORIZONTES DO ESTUDO TÉCNICO
# ============================================================

TECHNICAL_HORIZONS = [
    20,
    60,
    120,
    252,
]


# ============================================================
# 11. PARES QUE CHEGARAM À VALIDAÇÃO OOS
# ============================================================
#
# IMPORTANTE:
#
# Estes pares NÃO são gatilhos de produção.
#
# São preservados somente para rastreabilidade do estudo.
# Nenhum sobreviveu ao critério OOS completo.
# ============================================================

RESEARCH_OOS_PAIRS = [

    {
        "horizon": 60,
        "indicator_a": "SMA200_SLOPE_20D",
        "direction_a": "HIGH",
        "indicator_b": "ROC_60",
        "direction_b": "LOW",
        "survives_oos": False,
    },

    {
        "horizon": 120,
        "indicator_a": "SMA200_SLOPE_20D",
        "direction_a": "HIGH",
        "indicator_b": "ROC_60",
        "direction_b": "LOW",
        "survives_oos": False,
    },

    {
        "horizon": 252,
        "indicator_a": "ROC_60",
        "direction_a": "LOW",
        "indicator_b": "MACD_HIST_PCT",
        "direction_b": "HIGH",
        "survives_oos": False,
    },
]


# ============================================================
# 12. POLÍTICA DE INTEGRAÇÃO
# ============================================================

INTEGRATION_POLICY = {

    # Fundamentos determinam elegibilidade.
    "fundamental_first":
        True,

    # Quality continua sendo gate.
    "quality_gate_required":
        True,

    # Investabilidade continua obrigatória.
    "investability_required":
        True,

    # Valuation permanece separado do técnico.
    "valuation_separate":
        True,

    # Técnico é executado depois dos fundamentos.
    "technical_after_fundamental":
        True,

    # Técnico atualmente funciona como contexto.
    "technical_role":
        "ENTRY_CONTEXT",

    # Não existe veto técnico validado.
    "technical_veto":
        False,

    # Técnico não recupera empresa fundamentalmente reprovada.
    "technical_rescue":
        False,

    # Não existe score técnico final.
    "technical_score":
        False,
}


# ============================================================
# 13. ESTADOS FINAIS PERMITIDOS
# ============================================================

FINAL_STATUS = {

    "FUNDAMENTAL_FAILED":
        "INELEGIVEL",

    "FUNDAMENTAL_APPROVED":
        "ELEGIVEL",

    "VALUATION_PENDING":
        "AGUARDANDO_VALUATION",

    "TECHNICAL_CONTEXT_AVAILABLE":
        "CONTEXTO_TECNICO_DISPONIVEL",

    "TECHNICAL_CONTEXT_UNAVAILABLE":
        "CONTEXTO_TECNICO_INDISPONIVEL",
}


# ============================================================
# 14. REGRAS DE SEGURANÇA METODOLÓGICA
# ============================================================

METHODOLOGY_LOCK = {

    "allow_technical_to_change_quality_score":
        False,

    "allow_technical_to_change_valuation_score":
        False,

    "allow_technical_to_rescue_failed_company":
        False,

    "allow_unvalidated_pair_as_hard_trigger":
        False,

    "allow_arbitrary_technical_score":
        False,

    "allow_fundamental_ranking_without_quality_gate":
        False,
}


# ============================================================
# 15. VALIDAÇÃO DA CONFIGURAÇÃO
# ============================================================

def validate_config():

    errors = []

    if not FUNDAMENTAL_FIRST:
        errors.append(
            "FUNDAMENTAL_FIRST deve permanecer True."
        )

    if not QUALITY_IS_GATE:
        errors.append(
            "QUALITY_IS_GATE deve permanecer True."
        )

    if QUALITY_MIN_SCORE != 60.0:
        errors.append(
            "QUALITY_MIN_SCORE diferente da arquitetura congelada."
        )

    if MIN_HISTORY_YEARS != 10:
        errors.append(
            "MIN_HISTORY_YEARS deve permanecer em 10."
        )

    if MIN_AVG_DAILY_LIQUIDITY_BRL != 6_000_000.0:
        errors.append(
            "Liquidez mínima diferente da arquitetura congelada."
        )

    if abs(
        QUALITY_WEIGHT +
        VALUATION_WEIGHT -
        1.0
    ) > 1e-12:

        errors.append(
            "Pesos fundamentalistas não somam 100%."
        )

    if TECHNICAL_MANDATORY_TRIGGER:
        errors.append(
            "Não existe gatilho técnico obrigatório validado."
        )

    if TECHNICAL_CAN_RESCUE_FAILED_FUNDAMENTAL:
        errors.append(
            "Técnico não pode recuperar empresa "
            "reprovada nos fundamentos."
        )

    if TECHNICAL_SCORE_ENABLED:
        errors.append(
            "Technical Score não foi validado."
        )

    if OOS_VALIDATED_MANDATORY_PAIRS != 0:
        errors.append(
            "O estudo final possui zero pares "
            "obrigatórios validados OOS."
        )

    if len(
        TECHNICAL_CONTEXT_INDICATORS
    ) != 7:

        errors.append(
            "Esperados exatamente 7 indicadores "
            "técnicos preservados."
        )

    if errors:

        raise RuntimeError(
            "\n".join(errors)
        )

    return True


# ============================================================
# 16. EXECUÇÃO DIRETA
# ============================================================

if __name__ == "__main__":

    validate_config()

    print("=" * 70)
    print(PROJECT_NAME)
    print("=" * 70)

    print(
        f"Versão: {PROJECT_VERSION}"
    )

    print(
        f"Arquitetura: {ARCHITECTURE}"
    )

    print(
        f"Quality mínimo: {QUALITY_MIN_SCORE}"
    )

    print(
        f"Pesos: Quality {QUALITY_WEIGHT:.0%} | "
        f"Valuation {VALUATION_WEIGHT:.0%}"
    )

    print(
        "Technical Engine:",
        TECHNICAL_ENGINE_MODE
    )

    print(
        "Pares técnicos obrigatórios OOS:",
        OOS_VALIDATED_MANDATORY_PAIRS
    )

    print(
        "Indicadores técnicos de contexto:",
        len(TECHNICAL_CONTEXT_INDICATORS)
    )

    print(
        "\n✓ Configuração validada."
    )
