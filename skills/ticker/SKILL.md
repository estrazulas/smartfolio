---
name: investimentos-ticker
description: Analise completa de um ticker — estende a fundamentalista com previsoes de analistas, investimentos em andamento, riscos, forcas, perspectivas e veredito. Use quando o usuario pedir "analise WEGE3", "me fala sobre KNRI11", ou qualquer analise de ativo individual.
---

# Análise de Ticker

Estende `investimentos-fundamental-analyst` com camadas adicionais: projeções, investimentos, riscos, forças e veredito.

## Trigger

- "Analise WEGE3"
- "Me fala sobre <TICKER>"
- "O que acha de <TICKER>?"
- "Como está <TICKER>?"
- Qualquer pedido de análise de um ativo específico

## Fluxo

### Etapa 0 — Delegar a base

Carregar e executar `investimentos-fundamental-analyst` para o ticker.

**NÃO duplicar:** os fundamentos (P/L, ROE, margens, etc.) vêm dela. Esta skill só adiciona as camadas abaixo.

### Etapa 1 — Notícias e eventos

Carregar e executar `investimentos-earnings-reviewer` para o ticker. As notícias complementam a análise.

### Etapa 2 — Previsões de Analistas

Usar `web_search` com query:
```
"<TICKER> preço-alvo recomendação analistas 2026"
```

Apresentar em tabela:

| Casa | Recomendação | Preço-Alvo | Potencial |
|------|-------------|-----------|-----------|

### Etapa 3 — Investimentos em Andamento

Usar `web_search` com query:
```
"<TICKER> <NOME_EMPRESA> investimentos expansão fábrica aquisição"
```

Listar projetos com: valor, local, conclusão prevista, objetivo.

### Etapa 4 — Riscos e Fortalezas

Duas listas curtas (3-5 itens cada), baseadas nos dados coletados:

**🔴 Riscos:**
- Riscos específicos do ativo e do setor
- Ex: câmbio, regulação, concentração de clientes, commoditie

**🟢 Fortalezas:**
- Diferenciais competitivos
- Ex: ROIC elevado, caixa líquido, posição de mercado, diversificação

### Etapa 5 — Perspectivas (próximo trimestre)

O que esperar do próximo balanço, baseado nas notícias e projeções:
- Principais indicadores a monitorar
- Catalisadores positivos e negativos

### Etapa 6 — Veredito

Uma conclusão em 2-3 frases, contextualizando para o investidor de longo prazo.

Se o ativo fizer parte da carteira do usuário (verificar planilha/contexto), incluir:
- Peso atual vs alvo
- Se está acima ou abaixo
- Sugestão alinhada com o balanceamento

### Etapa 7 — Salvar (opcional)

`reports/analysis_<TICKER>_YYYY-MM-DD.md` no projeto smartfolio.

## Dependências

- `investimentos-fundamental-analyst` — NÃO duplicar, carregar via `skill_view`
- `investimentos-earnings-reviewer` — idem
- `web_search` + `web_extract` — para notícias e projeções
- `~/git/smartfolio/` — contexto do projeto (planilha, tickers)

## Regras

- SEMPRE carregar a fundamental-analyst primeiro (nunca pular)
- NUNCA repetir fundamentos que já estão na skill base — apenas referenciar
- Para tickers BR, buscar em portais BR (InfoMoney, Suno, Valor, Estadão)
- Para tickers US, buscar em portais US (CNBC, Reuters, SeekingAlpha)
- Citar fontes e datas em todas as seções
- Se web_search não retornar dados suficientes, informar "Dados limitados para este ativo"

## Pitfalls

- ETFs e cripto têm dados fundamentalistas limitados — a skill base já trata disso
- yfinance dividend yield subestima ativos BR — mencionar a ressalva
- Preços-alvo de analistas têm viés (casas de sell-side tendem a ser otimistas)
- Investimentos anunciados podem ser postergados — verificar se há atualizações recentes
