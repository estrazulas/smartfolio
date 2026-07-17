# Fontes de Notícias Recomendadas

Todas gratuitas. Ordenadas por tipo de ativo.

## Ações Brasileiras (ABCD3, etc.)

| # | Fonte | Feed | Foco |
|---|-------|------|------|
| 1 | **InfoMoney** | `https://www.infomoney.com.br/feed/` | Resultados, mercado, economia BR |
| 2 | **Suno** | `https://www.suno.com.br/noticias/feed/` | Dividendos, analises, recomendacoes |

## Ações Americanas / Globais

| # | Fonte | Feed | Foco |
|---|-------|------|------|
| 1 | **CNBC** | `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069` | Mercado US em tempo real |
| 2 | **Reuters** | `https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best` | Factual, sem vies, global |

## FIIs (FIII11, FOOO11, etc.)

| # | Fonte | Feed | Foco |
|---|-------|------|------|
| 1 | **InfoMoney FIIs** | `https://www.infomoney.com.br/setor/fiis/feed/` | Noticias do setor, dividendos, IFIX |
| 2 | **Suno** | `https://www.suno.com.br/noticias/feed/` | Analises de FIIs, renda passiva |

## ETFs (ETFF11, MCHI, SPHQ, etc.)

| # | Fonte | Feed | Foco |
|---|-------|------|------|
| 1 | **Investing.com** | `https://br.investing.com/rss/news.rss` | ETFs, indices, commodities |
| 2 | **Reuters** | `https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best` | Global, setorial |

## Cripto (BTC)

| # | Fonte | Feed | Acesso |
|---|-------|------|--------|
| 1 | **CoinTelegraph BR** | `https://cointelegraph.com.br/rss` | RSS direto ✅ |
| 2 | **BitNotícias** | `https://bitnoticias.com.br/feed/` | Cloudflare → usar `browser` ou `web_search` |

## Uso no fluxo de notícias

1. Identificar tipo do ativo (acao BR, FII, ETF, cripto, etc.)
2. Buscar feed RSS da fonte primaria
3. Se RSS bloqueado (ex: BitNoticias) → fallback: `web_search` com `site:bitnoticias.com.br <ticker>`
4. Extrair titulo, data, link
5. Filtrar por ticker mencionado no titulo
6. Priorizar ultimas 24-48h

## Pitfalls

- **BitNoticias RSS**: Cloudflare bloqueia `web_extract` e `curl`. Usar `browser` para acessar o feed ou `web_search` como fallback
- RSS do InfoMoney tem volume alto — filtrar por ticker, nao ler tudo
- Reuters feed e dinamico (query string) — testar antes de usar em producao
- Investing.com pode bloquear scrapers — usar web_search como fallback
- CNBC feed e XML puro — parsear com xml.etree
- Suno foca em recomendacoes, nao apenas noticias — filtrar o que e fato vs opiniao
- CoinTelegraph BR: feed RSS funcional, atualizado a cada hora, em portugues
