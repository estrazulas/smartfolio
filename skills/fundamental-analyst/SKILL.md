---
name: investimentos-fundamental-analyst
description: Analisa fundamentos de ativos de renda variavel (acoes, FIIs, ETFs) usando yfinance. Calcula P/L, ROE, Margem Liquida, Dividend Yield e compara com benchmarks. Use quando o usuario pedir analise fundamentalista, "como esta tal acao", ou ao gerar relatorio de investimentos.
---

# Fundamental Analyst

Analisa indicadores fundamentalistas de ativos de renda variavel.

## Trigger

- Usuario pede analise fundamentalista de um ou mais tickers
- "Como estao meus indicadores?"
- "Relatorio fundamentalista"
- Parte de rotina diaria/semanal de investimentos

## Fluxo

### 1. Identificar ativos

Receber lista de tickers do contexto (planilha, snapshot, ou mencao do usuario).
Filtrar: apenas acoes e FIIs tem dados fundamentalistas uteis. ETFs e cripto tem dados limitados — pular ou tratar separadamente.

### 2. Buscar dados

Usar `yfinance` para cada ticker:

```python
import yfinance as yf

t = yf.Ticker(ticker)
info = t.info

fundamentals = {
    "trailingPE": info.get("trailingPE"),
    "forwardPE": info.get("forwardPE"),
    "priceToBook": info.get("priceToBook"),
    "returnOnEquity": info.get("returnOnEquity"),
    "profitMargins": info.get("profitMargins"),
    "dividendYield": info.get("dividendYield"),
    "debtToEquity": info.get("debtToEquity"),
    "revenueGrowth": info.get("revenueGrowth"),
    "earningsGrowth": info.get("earningsGrowth"),
    "marketCap": info.get("marketCap"),
    "sector": info.get("sector"),
    "industry": info.get("industry"),
}
```

### 3. Interpretar com benchmarks

Usar `references/ratios-guide.md` como referencia de benchmarks.

| Indicador | Bom | Neutro | Ruim |
|-----------|-----|--------|------|
| ROE | > 15% | 8-15% | < 8% |
| P/L | < 15x | 15-25x | > 25x |
| Div Yield | > 6% | 3-6% | < 3% |
| Margem Liq | > 15% | 5-15% | < 5% |
| P/VP | < 2x | 2-4x | > 4x |
| Divida/PL | < 0.8 | 0.8-2 | > 2 |

Contextualizar por setor quando disponivel (`info["sector"]`).

### 4. Gerar analise

Formato livre, mas incluir:
- Nome do ativo e preco atual
- Indicadores-chave com semaforo (🟢 ok / 🟡 atencao / 🔴 ruim)
- Uma frase de conclusao por ativo
- Apenas ativos com dados disponiveis (pular os que yfinance nao retornar nada)

### 5. Salvar (opcional)

Se o projeto tiver pasta de reports, salvar em `reports/fundamentals_YYYY-MM-DD.md`.

## Pitfalls

- ETFs (ETFF11, SPHQ, etc.) e cripto NAO tem dados fundamentalistas — `info` vem quase vazio
- FIIs tem dados limitados (P/VP, dividendYield) mas ainda uteis
- Acoes brasileiras precisam sufixo `.SA`
- `info.get()` pode retornar None — sempre checar antes de usar
- Dados sao do ultimo balanco trimestral, nao tempo real
