# Investimentos Util

Utilitários para a planilha de investimentos via Composio + yfinance.

Skills baseadas em [anthropics/financial-services](https://github.com/anthropics/financial-services) e [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills).

## Setup rápido

```bash
cp .env.example .env          # preencher IDs reais + SHEET_WHITELIST
python3 -m venv .venv
.venv/bin/pip install yfinance python-dotenv
```

`.env`:
```
INVEST_SPREADSHEET_ID=<seu_id>
SHEET_WHITELIST=Dani Carteira,Ana Carteira   # apenas essas abas serao acessadas
```

## Estrutura

```
.env              → IDs das planilhas (gitignored)
sheets.json       → estrutura das abas, ticker mapping (gitignored)
snapshot.json     → cache do ultimo scan de tickers (gitignored)
plano.md          → plano completo do projeto (gitignored)
sync.py           → script principal: snapshot, check, update
daily_report.py   → relatorio diario: precos, macro, noticias, insights
skills/           → skills do Hermes (versionadas)
  fundamental-analyst/   → analise de P/L, ROE, Dividend Yield
  portfolio-rebalancer/  → peso alvo vs atual, sugestoes compra/venda
  earnings-reviewer/     → noticias, resultados, dividendos
scripts/
  daily_invest_report.sh → wrapper cron: .md + .pdf + email
reports/          → relatorios gerados (gitignored)
```

---

## Fluxo de sincronização (sync.py)

### 1. `sync.py snapshot` — tirar foto da planilha

Lê cada aba, encontra todos os tickers na coluna A, grava `snapshot.json` com posições (linha, coluna). Rodar sempre que adicionar/remover/renomear tickers na planilha.

### 2. `sync.py check` — verificar se algo mudou

Compara planilha atual vs `snapshot.json`. Se detectar ticker novo, removido ou movido de linha, mostra diff e sai com erro. Se nada mudou, sai OK.

### 3. `sync.py update` — atualizar preços

Roda `check` internamente. Se snapshot desatualizado, para e pede `snapshot` primeiro.
Se OK:
- Para cada ticker no snapshot, busca cotação (yfinance ou CoinGecko)
- Atualiza coluna C (preço atual) de cada ticker via Composio
- Loga o que foi alterado

---

## Ticker mapping (planilha → yfinance)

Regra no `sheets.json`:

| Padrão na planilha | yfinance |
|---------------------|----------|
| `XXXX11` (FIIs) | `XXXX11.SA` |
| `ABCD3` (ação BR) | `ABCD3.SA` |
| `BVMF:ABCD3` | `ABCD3.SA` |
| `NASDAQ:MCHI` | `MCHI` |
| `NYSEARCA:SPHQ` | `SPHQ` |
| `CURRENCY:BTCBRL` | CoinGecko API |

Mapeamento explícito no campo `ticker_map` do `sheets.json`.

---

## Estrutura da planilha (colunas)

| Col | Conteúdo |
|-----|----------|
| A | Ticker |
| B | Peso alvo (%) |
| C | Preço atual ← atualizado pelo sync.py |
| D | Quantidade |
| E | Peso na carteira |
| F | Valor alvo |
| G | Valor alocado |
| H | Diferença |

---

## Conexões Composio necessárias

```bash
composio connections list | grep -E "googlesheets|googledrive"
```

Devem estar ACTIVE. Para conectar: `composio link <toolkit> --no-browser --no-wait`

---

## Comandos rápidos (ad-hoc)

**Ler cabeçalho de uma aba:**
```bash
composio execute GOOGLESHEETS_BATCH_GET -d '{
  "spreadsheet_id": "'"$INVEST_SPREADSHEET_ID"'",
  "ranges": ["Dani Carteira!1:3"]
}'
```

**Buscar planilhas no Drive:**
```bash
composio execute GOOGLEDRIVE_FIND_FILE -d '{
  "q": "name contains \"invest\" and mimeType = \"application/vnd.google-apps.spreadsheet\" and trashed = false",
  "fields": "files(id,name,modifiedTime,webViewLink)",
  "orderBy": "modifiedTime desc"
}'
```

**Info completa da planilha:**
```bash
composio execute GOOGLESHEETS_GET_SPREADSHEET_INFO -d '{
  "spreadsheet_id": "'"$INVEST_SPREADSHEET_ID"'"
}'
```

---

## Fontes de dados

| Fonte | Cobertura | Custo |
|-------|-----------|-------|
| yfinance | Ações BR (.SA), FIIs, ETFs US, Ibovespa, IFIX | Grátis |
| CoinGecko | Bitcoin (BTC/BRL, BTC/USD) | Grátis |
| Banco Central | Selic meta, IPCA 12m | Grátis |
| Alpha Vantage | Fed Funds Rate | Grátis (demo key) |
| InfoMoney RSS | Manchetes do mercado BR | Grátis |
| Suno RSS | Notícias de FIIs | Grátis |

## Relatório diário (daily_report.py)

Gera `reports/daily_YYYY-MM-DD.md` + `.pdf` com 7 seções:

1. 📈 Oscilações Significativas (>3%)
2. 💰 Patrimônio (por carteira + total)
3. 🏦 Cenário Macro: Selic, CDI, IPCA, Juro Real, Fed Funds, Ibovespa, IFIX, Bitcoin USD
4. 📋 Tabela de ativos (preço + variação dia/semana/mês)
5. 📰 Destaques do Mercado (RSS InfoMoney + Suno)
6. 🌎 Notícias Macro (filtro por keywords: Selic, Copom, tarifa, etc.)
7. 💡 Insights & Recomendações (sentimento, RF vs bolsa)

### Uso

```bash
.venv/bin/python scripts/daily_report.py          # gera e salva
.venv/bin/python scripts/daily_report.py --print  # mostra no terminal tambem
```

### Cron job

Configurado como `no_agent: true` (zero tokens):
- **Schedule**: `0 12 * * *` (9h BRT)
- **Script**: `scripts/daily_invest_report.sh`
- **Faz**: sync.py update → daily_report.py → md-to-pdf → Gmail API
- **WhatsApp**: resumo curto (patrimônio, oscilações, índices, insights)
- **Email**: relatório completo `.md` + `.pdf` com links clicáveis

### PDF

Usa a skill `md-to-pdf` para converter `.md` → `.pdf` com hyperlinks preservados via Chrome headless. Requer `markdown` lib no venv.

## Pitfalls

- `GOOGLEDRIVE_FIND_FILE` usa campo `q` (não `query`)
- `GOOGLESHEETS_BATCH_GET` usa `ranges` (array), não `range`
- Tickers BR precisam sufixo `.SA` no yfinance
- `BVMF:` e `NASDAQ:` são prefixos da planilha — remover para yfinance
- BTC não funciona no yfinance em BRL — usar CoinGecko
- `composio execute` depende de conexão ativa (`composio connections list`)
- Sempre rodar `sync.py check` antes de `update` — nunca escrever às cegas

---

## Skills de Analise

As skills estao em `skills/` e linkadas em `~/.hermes/skills/`.

### investimentos-fundamental-analyst

Analisa P/L, ROE, Margem Liquida, Dividend Yield dos ativos.
Usa yfinance `t.info` para cada ticker (acoes e FIIs; ETFs e cripto sao pulados).
Referencia: `skills/fundamental-analyst/references/ratios-guide.md`

### investimentos-portfolio-rebalancer

Compara peso atual (coluna G / patrimonio total) vs peso alvo (coluna B).
Classifica em VENDER (>2% acima), COMPRAR (>2% abaixo), OK (dentro da banda).
Requer `sync.py update` rodado antes para precos atualizados.

### investimentos-earnings-reviewer

Busca noticias de cada ticker via `web_search` + `yfinance.news`.
Foco: dividendos anunciados, resultados trimestrais, alertas de risco.
Prioriza fontes BR (InfoMoney, Valor, Suno) para ativos .SA.

### Exemplo de uso

```
"Gere o relatorio fundamentalista"
"Minha carteira esta balanceada?"
"Tem noticia dos meus FIIs hoje?"
```
