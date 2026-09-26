# B3 INVESTMENT ENGINE

Sistema quantitativo para seleção e acompanhamento de ações brasileiras.

O projeto utiliza uma arquitetura **FUNDAMENTAL FIRST**, separando claramente a decisão fundamentalista do contexto técnico de entrada.

---

## Arquitetura

```text
CVM / Dados Fundamentais
        ↓
QUALITY ENGINE
        ↓
QUALITY GATE
        ↓
INVESTABILITY
10 anos + liquidez
        ↓
VALUATION
        ↓
FUNDAMENTAL RANKING
70% Quality + 30% Valuation
        ↓
TECHNICAL TIMING ENGINE
        ↓
INTEGRATION ENGINE
        ↓
FINAL REPORT
