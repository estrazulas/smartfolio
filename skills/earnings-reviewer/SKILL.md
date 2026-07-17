---
name: investimentos-earnings-reviewer
description: Busca noticias e eventos corporativos relevantes para ativos da carteira. Extrai highlights de resultados trimestrais, anuncios de dividendos, e alertas de risco. Use quando o usuario perguntar sobre noticias dos ativos, "o que saiu de resultado?", ou ao gerar monitor diario.
---

# Earnings Reviewer

Monitora noticias e eventos corporativos dos ativos da carteira.

## Trigger

- Usuario pede noticias de ativos especificos
- "O que saiu de resultado hoje?"
- "Tem dividendo anunciado?"
- Parte de rotina diaria de monitoramento

## Fluxo

### 1. Identificar ativos

Receber lista de tickers do contexto. Filtrar: acoes e FIIs tem eventos corporativos. ETFs passivos e cripto tem menos eventos relevantes.

### 2. Buscar noticias (RSS + web_search)

Consultar `references/news-sources.md` para feeds RSS por tipo de ativo.

**Prioridade:** RSS feed → web_search fallback.

```python
t = yf.Ticker(ticker)
news = t.news  # noticias recentes (mais util para ativos US)
dividends = t.dividends  # historico de pagamentos
```

### 3. Filtrar e classificar

Manter apenas noticias especificas do ticker (ignorar noticias genericas de mercado).

| Tag | Criterio |
|-----|----------|
| 🔔 DIVIDENDO | Anuncio de pagamento, data-com, data-ex, valor |
| 📊 RESULTADO | Lucro/prejuizo trimestral, guidance, revisao de projecoes |
| ⚠️ RISCO | Governanca, regulacao, investigacoes, recalls |
| 📈 EVENTO | Fusoes, aquisicoes, IPO, follow-on, reestruturacao |

### 4. Verificar dividendos proximos

Para cada ativo, verificar `t.dividends` dos ultimos 90 dias.
Se houver pagamento com data-ex nos proximos 30 dias, incluir no relatorio.

### 5. Gerar relatorio

Agrupar por tipo de evento. Para cada noticia:
- Ticker e nome do ativo
- Tag de classificacao
- Resumo em 1-2 frases
- Fonte e data

### 6. Salvar (opcional)

`reports/earnings_YYYY-MM-DD.md`

## Regras

- Max 5 noticias por ticker por dia
- SEMPRE citar fonte e data
- Priorizar fontes locais: ativos BR → portais BR, ativos US → portais US/internacionais
- Se nenhuma noticia relevante, informar "Sem eventos relevantes no periodo"
- Nao repetir a mesma noticia de fontes diferentes

## Pitfalls

- `web_search` tem limite de chamadas — agrupar multiplos tickers na mesma query quando possivel
- yfinance `t.news` funciona melhor para ativos US do que BR
- ETFs (ETFF11, SPHQ) nao tem earnings calls — mencionar apenas se houver noticia de mercado relevante
- Verificar se a noticia e realmente sobre o ticker e nao sobre outra empresa com nome similar
