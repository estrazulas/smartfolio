# Smartfolio

Monitoramento automatizado de carteira de investimentos com Hermes Agent.
Relatório diário com preços, indicadores macro, notícias e insights de balanceamento.

## Funcionalidades

- 📊 **Relatório diário** com 7 seções: oscilações, patrimônio, cenário macro (Selic, Fed, Ibovespa, IFIX, BTC), tabela de ativos, destaques do mercado, notícias macro e insights
- 🔄 **Sincronização de preços** via yfinance + CoinGecko direto na planilha do Google Sheets
- 🧠 **Skills de análise**: fundamentalista (P/L, ROE, dividend yield), rebalanceamento de carteira, monitor de notícias
- 🤖 **Cron job automático**: 9h BRT com entrega via WhatsApp + email

## Créditos

As skills de análise são adaptadas de:

- [anthropics/financial-services](https://github.com/anthropics/financial-services) — templates de análise financeira
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) — scripts de valuation e ratio analysis

## Setup

### 1. Clone

```bash
git clone <seu-repo> investimentos_util
cd investimentos_util
```

### 2. Configurar

```bash
cp .env.example .env
cp sheets.example.json sheets.json
```

Edite `.env` com seus dados:

```bash
INVEST_SPREADSHEET_ID=<id-da-sua-planilha>
SHEET_WHITELIST=Minha Carteira,Outra Carteira
ALPHA_VANTAGE_KEY=  # opcional, melhora dados de ações BR
```

### 3. Ambiente Python

```bash
python3 -m venv .venv
.venv/bin/pip install yfinance python-dotenv markdown
```

### 4. Conectar Google Sheets (Composio)

```bash
composio link googlesheets --no-browser --no-wait
composio link googledrive --no-browser --no-wait
# Abra a URL de cada um no navegador e autorize
```

### 5. Preencher sheets.json

Rode para sua planilha e cole a saída no `sheets.json`:

```bash
composio execute GOOGLESHEETS_GET_SPREADSHEET_INFO -d '{"spreadsheet_id": "<seu-id>"}'
```

### 6. Primeiro snapshot

```bash
.venv/bin/python scripts/sync.py snapshot
```

## Uso

### Comandos

```bash
# Atualizar preços na planilha
.venv/bin/python scripts/sync.py update

# Verificar se a planilha mudou desde o último snapshot
.venv/bin/python scripts/sync.py check

# Gerar relatório diário completo
.venv/bin/python scripts/daily_report.py --print
```

### Skills do Hermes

As skills ficam em `skills/` e são linkadas automaticamente em `~/.hermes/skills/`:

```
"analise ABCD3"              → Fundamental Analyst
"gere relatório de balanceamento" → Portfolio Rebalancer
"tem notícia dos meus FIIs?" → Earnings Reviewer
```

### Cron job diário

O script `scripts/daily_invest_report.sh` gera o relatório `.md` + `.pdf` e envia por email (Gmail API).
Configure um cron job no Hermes:

```
schedule: 0 12 * * *     # 9h BRT
script: daily_invest_report.sh
no_agent: true
deliver: whatsapp          # resumo curto
email: via gmail_send_attach.py no próprio script
```

---

## Modelo de Planilha

Sua planilha deve seguir esta estrutura de colunas (a partir da linha 5):

| A (Ticker) | B (Peso Alvo) | C (Preço Atual) | D (Qtd) | E (Peso) | F (Valor Alvo) | G (Alocado) | H (Diferença) |
|------------|---------------|-----------------|---------|----------|----------------|-------------|---------------|
| ABCD3      | 15%           |                 | 100     | 15       |                |             |               |
| FIII11     | 20%           |                 | 50      | 20       |                |             |               |
| MCHI       | 10%           |                 | 30      | 10       |                |             |               |

**Regras:**
- **Linhas 1-3**: totais da carteira (Total BR, Total US, Total Geral)
- **Linha 4**: cabeçalho da seção ("Ações BR", "FIIs", "Equity", etc.)
- **Linhas 5+**: ativos com ticker na coluna A
- **Coluna C**: preenchida automaticamente pelo `sync.py update`
- **Tickers BR**: ações (ex: ABCD3, XYZB4), FIIs (ex: FIII11, FOOO11)
- **Tickers US**: prefixo `NASDAQ:` ou `NYSEARCA:` (ex: `NASDAQ:MCHI`, `NYSEARCA:SPHQ`)
- **BTC**: `CURRENCY:BTCBRL` (BRL) ou `BTCUSD` (USD)
- **Linhas de categoria**: "Ações BR", "RF", "Caixa", "FIIs", "Equity", "Proteções" — são ignoradas pelo scanner

### Ticker mapping

No `sheets.json`, mapeie como cada ticker da planilha é buscado:

```json
{
  "ticker_map": {
    "ABCD3": "ABCD3.SA",
    "FIII11": "FIII11.SA",
    "NASDAQ:MCHI": "MCHI",
    "NYSEARCA:SPHQ": "SPHQ",
    "CURRENCY:BTCBRL": "COINGECKO:BTC/BRL",
    "BTCUSD": "COINGECKO:BTC/USD"
  }
}
```

### Exemplo mínimo

Crie uma planilha no Google Sheets com 2 abas: `Dani Carteira` e `Ana Carteira` (ou os nomes que preferir).

**Aba "Minha Carteira":**

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| | | | | Total Geral | | | |
| | | | | Total BR | R$ 0,00 | | |
| | | | | Total US | R$ 0,00 | | |
| Ações BR | | | QTD | Peso | Alvo | Alocado | Diff |
| ABCD3 | 50% | | 100 | 50 | R$ 0,00 | R$ 0,00 | |
| FIIs | 30% | | | 30 | R$ 0,00 | R$ 0,00 | |
| FIII11 | 100% | | 50 | 30 | R$ 0,00 | R$ 0,00 | |
| Equity | 20% | | | 20 | R$ 0,00 | R$ 0,00 | |
| NASDAQ:MCHI | 100% | | 30 | 20 | R$ 0,00 | R$ 0,00 | |

## Estrutura do Projeto

```
├── .env.example          → template de variáveis
├── sheets.example.json   → template de mapeamento
├── CLAUDE.md             → instruções para agentes
├── sync.py               → snapshot | check | update (preços)
├── daily_report.py       → relatório diário completo
├── skills/               → skills do Hermes
│   ├── fundamental-analyst/
│   ├── portfolio-rebalancer/
│   └── earnings-reviewer/
├── scripts/
│   └── daily_invest_report.sh  → wrapper do cron job
└── reports/              → saída dos relatórios (gitignored)
```

## Fontes de Dados

| Fonte | Uso | Custo |
|-------|-----|-------|
| yfinance | Preços, histórico, fundamentos | Grátis |
| CoinGecko | Bitcoin BRL/USD | Grátis |
| Banco Central | Selic, IPCA | Grátis |
| Alpha Vantage | Fed Funds | Grátis (demo key) |
| InfoMoney RSS | Manchetes do mercado | Grátis |
| Suno RSS | Notícias de FIIs | Grátis |

## Limitações

- Limite de 25 req/dia no Alpha Vantage free tier (Fed Funds usa demo key)
- yfinance pode ter atraso de ~15min em cotações
- Dados fundamentalistas de ações BR no yfinance são limitados — Alpha Vantage complementa
- `GOOGLESHEETS_BATCH_UPDATE` escreve a partir de A1 — o script padroniza colunas para evitar corrupção
