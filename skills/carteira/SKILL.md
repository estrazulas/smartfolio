---
name: investimentos-carteira
description: Orquestrador da carteira de investimentos. Le o relatorio diario, discute os numeros e entao pergunta ao usuario se quer acionar cada skill de analise individualmente. Use quando o usuario disser "/carteira", "como esta minha carteira?", "analisar investimentos", ou perguntar sobre a carteira de forma geral.
---

# Carteira — Orquestrador de Analise

Fluxo completo de analise da carteira: relatorio diario → skills sob demanda.

## Trigger

- `/carteira`
- "Como esta minha carteira?"
- "Analisar investimentos"
- "O que faco com meus investimentos hoje?"
- Qualquer pergunta generica sobre a carteira que nao seja especifica de balanceamento, fundamentos ou noticias

## Fluxo

### Etapa 1 — Ler e discutir o relatório diário

1. Encontrar o relatório mais recente com `ls -t ~/git/investimentos_util/reports/daily_*.md | head -1` via terminal (NUNCA usar `search_files` — o glob não funciona nessa pasta)
2. Se não houver arquivo `.md`, pular direto pra Etapa 2
3. Apresentar um resumo executivo:
   - Patrimonio total por carteira
   - Maiores altas e quedas (>3%)
   - Cenário macro (Selic, IPCA, juro real, Ibovespa, IFIX, Bitcoin)
   - Insights do relatorio
3. Discutir os numeros: o que chama atencao, tendencias, alertas

### Etapa 2 — Perguntar quais skills acionar

Apos discutir o relatorio, perguntar **uma skill por vez** se o usuario quer acionar:

> "Quer que eu rode o **rebalanceamento** da carteira pra ver o que esta fora do peso alvo? (s/n)"

- Se **sim**: carregar `investimentos-portfolio-rebalancer` e executar:
  1. Puxar dados da planilha via `composio execute GOOGLESHEETS_BATCH_GET`
  2. Calcular desvios peso atual vs alvo
  3. Classificar: COMPRAR, VENDER, ATENCAO, OK
  4. Apresentar tabela com acoes sugeridas e valores

> "Quer que eu busque **noticias e eventos** dos ativos? Dividendos, resultados, alertas? (s/n)"

- Se **sim**: carregar `investimentos-earnings-reviewer` e executar:
  1. Para ativos com maiores oscilacoes + desbalanceados, buscar noticias
  2. Usar yfinance (`t.news`, `t.dividends`) no venv `~/git/investimentos_util/.venv/`
  3. Priorizar tickers BR (ações, FIIs) e ativos com quedas >5%
  4. Classificar: DIVIDENDO, RESULTADO, RISCO, EVENTO
  5. Apresentar em tabela com tag e fonte

> "Quer que eu rode a **analise fundamentalista**? P/L, ROE, Dividend Yield? (s/n)"

- Se **sim**: carregar `investimentos-fundamental-analyst` e executar:
  1. Para acoes e FIIs (pular ETFs e cripto), buscar fundamentos via yfinance
  2. Calcular P/L, ROE, Margem Liquida, Dividend Yield
  3. Comparar com benchmarks
  4. Apresentar tabela comparativa

### Etapa 3 — Finalizar

> "Quer que eu atualize os precos na planilha? (s/n)"

- Se sim: `cd ~/git/investimentos_util && .venv/bin/python3 sync.py check && .venv/bin/python3 sync.py update`

Resumo final com as decisoes tomadas.

## Dependencias

- `~/git/investimentos_util/` — repo com relatorios, sync.py, .venv
- `composio` — CLI em `~/.composio/composio` para acessar Google Sheets
- Skills irmaos: `investimentos-portfolio-rebalancer`, `investimentos-earnings-reviewer`, `investimentos-fundamental-analyst`

## Pitfalls

- ⚠️ **NUNCA usar `search_files` para achar o relatório** — o glob não funciona na pasta `reports/`. Usar sempre `terminal` com `ls -t ~/git/investimentos_util/reports/daily_*.md | head -1`
- Relatório diário pode não existir ainda no dia — nesse caso, pular etapa 1 e ir direto pra etapa 2
- Se `composio` falhar, avisar o usuario (pode ser path)
- Se Firecrawl/web_search falhar, usar yfinance como fallback para noticias
- FIIs BR: yfinance nao captura bem dividendos — mencionar a limitacao
- Nunca pular a etapa de perguntar — o usuario decide quais skills rodar
