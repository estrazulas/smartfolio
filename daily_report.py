#!/usr/bin/env python3
"""daily_report.py — Relatorio diario de investimentos.

Gera um Markdown com:
- Cenario Macro (Selic, IPCA, CDI, Fed Funds, Tesouro)
- Variacao de preco (dia, semana, mes) por ativo
- Ativos com >3% de oscilacao
- Patrimonio total por carteira
- Noticias dos ativos (RSS)
- Noticias macro (juros, inflacao, politica)
- Insights e recomendacoes (balanceamento, alertas)

Uso:
    daily_report.py           Gera relatorio e salva em reports/
    daily_report.py --print   Mostra no terminal tambem
"""

import json
import os
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
SHEETS_FILE = PROJECT_DIR / "sheets.json"
SNAPSHOT_FILE = PROJECT_DIR / "snapshot.json"
REPORTS_DIR = PROJECT_DIR / "reports"

load_dotenv(ENV_FILE)
SPREADSHEET_ID = os.environ["INVEST_SPREADSHEET_ID"]


def load_snapshot() -> dict:
    with open(SNAPSHOT_FILE) as f:
        return json.load(f)


def load_ticker_map() -> dict:
    with open(SHEETS_FILE) as f:
        return json.load(f)["ticker_map"]


def composio(action: str, payload: dict) -> dict:
    composio_bin = os.path.expanduser("~/.composio/composio")
    cmd = [composio_bin, "execute", action, "-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    if not data.get("successful"):
        raise RuntimeError(f"composio: {data.get('error')}")
    return data


def resolve_ticker(sheet_ticker: str, ticker_map: dict) -> tuple[str, str]:
    """(source, symbol). source = yfinance | coingecko."""
    mapped = ticker_map.get(sheet_ticker, sheet_ticker)
    if mapped.startswith("COINGECKO:"):
        return "coingecko", mapped.split(":", 1)[1]
    return "yfinance", mapped


def fetch_price_history(symbol: str, source: str) -> dict:
    """Retorna {current, day_ago, week_ago, month_ago}."""
    if source == "coingecko":
        return fetch_coingecko_history(symbol)

    try:
        t = yf.Ticker(symbol)
        # Preco atual
        current = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPreviousClose")
        if not current:
            return {}

        # Historico (ultimos 45 dias cobre 1 mes)
        hist = t.history(period="45d")
        if hist.empty:
            return {"current": current}

        def closest_price(days_back: int):
            target = hist.index[-1] - pd.Timedelta(days=days_back)
            idx = hist.index.get_indexer([target], method="nearest")[0]
            return hist["Close"].iloc[idx]

        import pandas as pd

        return {
            "current": current,
            "day_ago": closest_price(1) if len(hist) > 1 else None,
            "week_ago": closest_price(7) if len(hist) > 5 else None,
            "month_ago": closest_price(30) if len(hist) > 21 else None,
        }
    except Exception as e:
        print(f"  ⚠️ {symbol}: {e}")
        return {}


def fetch_coingecko_history(pair: str) -> dict:
    """BTC via CoinGecko (so preco atual + 24h)."""
    coin_map = {"BTC/BRL": "bitcoin", "BTC/USD": "bitcoin"}
    currency_map = {"BTC/BRL": "brl", "BTC/USD": "usd"}
    coin = coin_map.get(pair)
    currency = currency_map.get(pair, "usd")
    if not coin:
        return {}
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&community_data=false&developer_data=false"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        current = resp["market_data"]["current_price"].get(currency)
        change_24h = resp["market_data"]["price_change_percentage_24h_in_currency"].get(currency)
        change_7d = resp["market_data"]["price_change_percentage_7d_in_currency"].get(currency)
        change_30d = resp["market_data"]["price_change_percentage_30d_in_currency"].get(currency)

        result = {"current": current}
        if change_24h is not None:
            result["day_ago"] = current / (1 + change_24h / 100) if change_24h != -100 else None
        if change_7d is not None:
            result["week_ago"] = current / (1 + change_7d / 100) if change_7d != -100 else None
        if change_30d is not None:
            result["month_ago"] = current / (1 + change_30d / 100) if change_30d != -100 else None
        return result
    except Exception as e:
        print(f"  ⚠️ CoinGecko {pair}: {e}")
        return {}


def classify_ticker(ticker: str) -> str:
    """Classifica ticker: acao_br | fii | etf | cripto."""
    if ticker in ("CURRENCY:BTCBRL", "BTCUSD"):
        return "cripto"
    if any(ticker.startswith(p) for p in ("NASDAQ:", "NYSEARCA:")):
        return "etf"
    if ticker.endswith("11"):
        return "fii"
    return "acao_br"


def fetch_asset_news(tickers: list[str]) -> list[dict]:
    """Busca manchetes do mercado nos RSS (sem filtrar por ticker)."""
    news_items = []
    feeds = [
        ("InfoMoney", "https://www.infomoney.com.br/feed/"),
        ("Suno", "https://www.suno.com.br/noticias/feed/"),
    ]
    for name, feed_url in feeds:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            tree = ET.parse(resp)
            items = tree.findall(".//item")
            for item in items[:5]:  # top 5 por feed
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
                if title and len(title) > 15:
                    news_items.append({
                        "ticker": "MERCADO",
                        "title": title,
                        "link": link,
                        "source": name,
                    })
        except Exception as e:
            print(f"  ⚠️ RSS {name}: {e}")
    return news_items


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "  -   "
    color = "🔴" if value < -3 else ("🟢" if value > 3 else "")
    return f"{color}{value:+.1f}%"


def fmt_brl(value: float) -> str:
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- Macro ---

def fetch_selic() -> dict:
    """Busca Selic e IPCA via API publica do Banco Central."""
    try:
        # Selic meta (% a.a.)
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        selic = float(resp[0]["valor"]) if resp else None

        # IPCA acumulado 12 meses
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        ipca = float(resp[0]["valor"]) if resp else None

        return {"selic": selic, "ipca_12m": ipca}
    except Exception as e:
        print(f"  ⚠️ BCB: {e}")
        return {}


def fetch_fed_funds() -> dict:
    """Busca Fed Funds Rate via Alpha Vantage (gratuito)."""
    try:
        url = "https://www.alphavantage.co/query?function=FEDERAL_FUNDS_RATE&interval=monthly&apikey=demo"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        rate = float(resp["data"][0]["value"]) if resp.get("data") else None
        return {"fed_funds": rate}
    except Exception as e:
        print(f"  ⚠️ Fed: {e}")
        return {}


def fetch_indices() -> dict:
    """Busca Ibovespa, IFIX e BTC/USD via yfinance."""
    import math
    result = {}
    indices = {"IBOV": "^BVSP", "IFIX": "IFIX.SA", "BTC": "BTC-USD"}
    for name, ticker in indices.items():
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.get("lastPrice")

            def valid(v):
                return v is not None and not (isinstance(v, float) and math.isnan(v))

            prev = None
            for key in ("regularMarketPreviousClose", "previousClose"):
                v = info.get(key)
                if valid(v):
                    prev = v
                    break

            if price and valid(price) and prev:
                pct = (price / prev - 1) * 100
            elif price and valid(price):
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    pct = (price / prev - 1) * 100
                else:
                    pct = None
            else:
                continue
            result[name] = {"price": price, "change_pct": pct}
        except Exception as e:
            print(f"  ⚠️ Indice {name}: {e}")
    return result


MACRO_RSS = [
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
    ("Investing.com", "https://br.investing.com/rss/news.rss"),
]

MACRO_KEYWORDS = [
    "SELIC", "JUROS", "COPOM", "IPCA", "INFLAÇÃO", "INFLAcaO",
    "TESOURO DIRETO", "TESOURO", "TÍTULOS PÚBLICOS", "TITULOS",
    "FED", "FOMC", "BANCO CENTRAL", "BACEN",
    "RENDA FIXA", "CDI", "PIB", "CÂMBIO", "CAMBIAL", "DÓLAR",
    "FISCAL", "DÍVIDA", "TAXA", "TREASURY", "BOND",
    "TARIFA", "TARIFAÇO", "EUA", "IBOVESPA", "BOLSA",
]


def fetch_macro_news() -> list[dict]:
    """Busca noticias macro nos RSS e filtra por keywords."""
    macro_items = []
    for name, feed_url in MACRO_RSS:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            tree = ET.parse(resp)
            items = tree.findall(".//item")
            for item in items[:10]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
                if not title:
                    continue
                title_upper = title.upper()
                if any(kw in title_upper for kw in MACRO_KEYWORDS):
                    macro_items.append({"title": title, "link": link, "source": name})
        except Exception as e:
            print(f"  ⚠️ RSS macro {name}: {e}")
    return macro_items[:8]  # max 8


def generate_insights(all_assets: dict, portfolios: dict, macro: dict, macro_us: dict, indices: dict) -> list[str]:
    """Gera insights baseados nos dados do dia."""
    insights = []

    # --- Alertas de variacao >5% ---
    snapshot = load_snapshot()
    for sheet_name, snap_data in snapshot["sheets"].items():
        assets = all_assets.get(sheet_name, {})
        if not assets:
            continue
        for ticker in snap_data["tickers"]:
            prices = assets.get(ticker, {})
            if not prices.get("current"):
                continue
            day_pct = ((prices["current"] / prices["day_ago"] - 1) * 100) if prices.get("day_ago") else None
            if day_pct and abs(day_pct) > 5:
                direction = "subiu" if day_pct > 0 else "caiu"
                insights.append(f"⚠️ **{ticker}** {direction} {abs(day_pct):.1f}% hoje ({sheet_name})")

    # --- Renda Fixa vs Bolsa ---
    selic = macro.get("selic")
    ipca = macro.get("ipca_12m")
    if selic:
        real = (1 + selic / 100) / (1 + ipca / 100) - 1 if ipca else selic * 0.7
        insights.append(f"🏦 **Selic {selic:.1f}%** — Renda Fixa paga ~{selic*0.7:.1f}% liq IR. Juro real de ~{real*100:.1f}% a.a.")

    # --- Mercado (Ibovespa / IFIX) ---
    if "IBOV" in indices:
        ibov = indices["IBOV"]
        direction = "subiu" if ibov["change_pct"] > 0 else "caiu"
        if abs(ibov["change_pct"]) > 1:
            insights.append(f"📊 **Ibovespa {direction} {abs(ibov['change_pct']):.1f}%** — {'bolsa reagindo a noticias' if abs(ibov['change_pct']) > 2 else 'movimento moderado'}")
    if "IFIX" in indices:
        ifix = indices["IFIX"]
        direction = "subiu" if ifix["change_pct"] > 0 else "caiu"
        insights.append(f"🏢 **IFIX {direction} {abs(ifix['change_pct']):.1f}%** — {'FIIs em movimento' if abs(ifix['change_pct']) > 0.5 else 'FIIs estaveis'}")

    # --- BTC ---
    if "BTC" in indices:
        btc = indices["BTC"]
        direction = "subiu" if btc["change_pct"] > 0 else "caiu"
        if abs(btc["change_pct"]) > 2:
            insights.append(f"₿ **Bitcoin {direction} {abs(btc['change_pct']):.1f}%** — volatilidade elevada, atencao")

    # --- Fed / US ---
    if macro_us.get("fed_funds"):
        insights.append(f"🇺🇸 **Fed Funds {macro_us['fed_funds']:.2f}%** — {'juros altos favorecem renda fixa em dolar' if macro_us['fed_funds'] > 3 else 'juros em queda favorecem bolsa americana'}")

    # --- Sentimento geral ---
    sentiment_parts = []
    if selic and ipca and selic > ipca + 5:
        sentiment_parts.append("juro real elevado favorece renda fixa BR")
    if "IBOV" in indices and indices["IBOV"]["change_pct"] < -1:
        sentiment_parts.append("bolsa em queda pode ser oportunidade de compra")
    elif "IBOV" in indices and indices["IBOV"]["change_pct"] > 1:
        sentiment_parts.append("bolsa em alta, cautela com novos aportes")
    if "IFIX" in indices and indices["IFIX"]["change_pct"] < -0.5:
        sentiment_parts.append("FIIs descontados, bons yields")
    if sentiment_parts:
        insights.append(f"🧭 **Sentimento**: {', '.join(sentiment_parts)}")

    if not insights:
        insights.append("✅ Nenhum alerta relevante hoje.")

    return insights


def main():
    print_stdout = "--print" in sys.argv

    # 1. Garantir precos atualizados
    print("📊 sync.py update...")
    subprocess.run(
        [sys.executable, str(PROJECT_DIR / "sync.py"), "update"],
        capture_output=not print_stdout,
    )

    # 2. Carregar dados
    snapshot = load_snapshot()
    ticker_map = load_ticker_map()
    today = datetime.now(timezone.utc)

    # 3. Buscar historico de precos
    print("📈 Buscando historico de precos...")
    all_assets = {}  # {sheet_name: {ticker: {current, day_ago, ...}}}
    all_tickers_set = set()

    for sheet_name, snap_data in snapshot["sheets"].items():
        all_assets[sheet_name] = {}
        for ticker in snap_data["tickers"]:
            source, symbol = resolve_ticker(ticker, ticker_map)
            prices = fetch_price_history(symbol, source)
            if prices:
                all_assets[sheet_name][ticker] = prices
            all_tickers_set.add(ticker)

    # 4. Buscar patrimonio
    print("💰 Lendo patrimonio...")
    portfolios = {}
    for sheet_name in snapshot["sheets"]:
        cfg = None
        ss = load_ticker_map()
        with open(SHEETS_FILE) as f:
            sheets_cfg = json.load(f)["spreadsheets"][SPREADSHEET_ID]["sheets"]
            cfg = sheets_cfg.get(sheet_name)

        if not cfg:
            continue

        # Le coluna G (alocado) + total
        max_col = "H"  # colunas A-H bastam
        last_row = max(
            p["row"] for p in snapshot["sheets"][sheet_name]["positions"].values()
        ) + 2

        data = composio("GOOGLESHEETS_BATCH_GET", {
            "spreadsheet_id": SPREADSHEET_ID,
            "ranges": [f"{sheet_name}!A1:{max_col}{last_row}"],
        })
        rows = data["data"]["valueRanges"][0].get("values", [])

        # Procura "Total Btg" ou "Total Inter" nas primeiras linhas
        total = 0
        for row in rows[:5]:
            for i, cell in enumerate(row):
                if isinstance(cell, str) and ("Total Btg" in cell or "Total Inter" in cell or "Total" in cell):
                    for c in row:
                        if isinstance(c, str) and "R$" in c:
                            try:
                                val = c.replace("R$", "").replace(".", "").replace(",", ".")
                                total = max(total, float(val))  # pega o maior
                            except ValueError:
                                pass
                            break

        portfolios[sheet_name] = total

    # 5. Buscar noticias
    print("📰 Buscando noticias...")
    all_tickers = list(all_tickers_set)
    news = fetch_asset_news(all_tickers)

    # 5b. Buscar noticias macro
    print("🌎 Buscando noticias macro...")
    macro_news = fetch_macro_news()

    # 5c. Buscar dados macro
    print("🏦 Buscando indicadores macro...")
    macro_data = fetch_selic()
    fed_data = fetch_fed_funds()
    indices = fetch_indices()

    # 5d. Gerar insights
    print("💡 Gerando insights...")
    insights = generate_insights(all_assets, portfolios, macro_data, fed_data, indices)

    # 6. Gerar relatorio
    report = []
    date_str = today.strftime("%d/%m/%Y")
    file_date = today.strftime("%Y-%m-%d")

    report.append(f"# 📊 Relatório Diário — {date_str}\n")

    # --- Variacoes >3% ---
    report.append("## 📈 Oscilações Significativas (>3%)\n")
    alertas = []
    seen_alerts = set()
    for sheet_name, assets in all_assets.items():
        for ticker, prices in assets.items():
            if not prices.get("current") or not prices.get("day_ago"):
                continue
            pct = (prices["current"] / prices["day_ago"] - 1) * 100
            key = (ticker, abs(pct))
            if abs(pct) > 3 and key not in seen_alerts:
                seen_alerts.add(key)
                emoji = "🟢" if pct > 0 else "🔴"
                currency = "US$" if any(
                    p in ticker for p in ("NASDAQ:", "NYSEARCA:")
                ) else "R$"
                price_fmt = f"{currency} {prices['current']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                alertas.append(f"  {emoji} **{ticker}**: {pct:+.1f}% ({price_fmt})")

    if alertas:
        report.extend(alertas)
    else:
        report.append("  Nenhum ativo com oscilação >3% no dia.\n")
    report.append("")

    # --- Patrimonio ---
    report.append("## 💰 Patrimônio\n")
    total_geral = sum(portfolios.values())
    for name, val in sorted(portfolios.items()):
        report.append(f"  **{name}**: {fmt_brl(val)}")
    report.append(f"\n  **Total geral**: {fmt_brl(total_geral)}\n")

    # --- Cenário Macro ---
    report.append("## 🏦 Cenário Macro\n")
    if macro_data.get("selic"):
        report.append(f"  **Selic**: {macro_data['selic']:.1f}% a.a.")
        report.append(f"  **CDI**: ~{macro_data['selic'] - 0.1:.1f}% a.a. (≈ Selic - 0.1pp)")
        report.append(f"  **CDB 100% CDI (liq IR)**: ~{macro_data['selic'] * 0.7:.1f}% a.a. (aliquota 30%)")
        report.append(f"  **Poupança**: ~{macro_data['selic'] * 0.7 * 0.6:.1f}% a.a. (70% da Selic)")
    if macro_data.get("ipca_12m"):
        report.append(f"  **IPCA 12m**: {macro_data['ipca_12m']:.2f}%")
        if macro_data.get("selic"):
            real = (1 + macro_data['selic'] / 100) / (1 + macro_data['ipca_12m'] / 100) - 1
            report.append(f"  **Juro Real**: ~{real * 100:.1f}% a.a.")
    if fed_data.get("fed_funds"):
        report.append(f"\n  🇺🇸 **Fed Funds**: {fed_data['fed_funds']:.2f}% a.a.")
        report.append(f"  **Treasury 10Y**: referencia para renda fixa em USD")
    if indices:
        report.append("")
        for name in ["IBOV", "IFIX", "BTC"]:
            if name in indices:
                d = indices[name]
                emoji = "🟢" if (d["change_pct"] or 0) > 0 else "🔴"
                label = {"IBOV": "Ibovespa", "IFIX": "IFIX", "BTC": "Bitcoin USD"}[name]
                fmt = f"R$ {d['price']:,.0f}" if name in ("IBOV", "IFIX") else f"$ {d['price']:,.0f}"
                fmt = fmt.replace(",", "X").replace(".", ",").replace("X", ".")
                pct_str = f"({d['change_pct']:+.1f}%)" if d["change_pct"] is not None else ""
                report.append(f"  {emoji} **{label}**: {fmt} {pct_str}")
    report.append("")

    # --- Tabela completa ---
    report.append("## 📋 Todos os Ativos\n")
    report.append("| Ticker | Preço | Dia | Semana | Mês |")
    report.append("|--------|-------|-----|--------|-----|")

    for sheet_name in ["Dani Carteira", "Ana Carteira"]:
        assets = all_assets.get(sheet_name, {})
        if not assets:
            continue
        report.append(f"| **{sheet_name}** | | | | |")
        for ticker, prices in assets.items():
            if not prices.get("current"):
                continue

            current = prices["current"]
            is_us = any(p in ticker for p in ("NASDAQ:", "NYSEARCA:"))
            currency = "US$" if is_us else "R$"

            # BTC/BRL vs BTC/USD
            if ticker == "CURRENCY:BTCBRL":
                price_str = f"{fmt_brl(current)}"
            elif ticker == "BTCUSD":
                price_str = f"$ {current:,.0f}"
            elif is_us:
                price_str = f"$ {current:,.2f}"
            else:
                price_str = f"R$ {current:,.2f}".replace(".", ",")

            day_pct = ((current / prices["day_ago"] - 1) * 100) if prices.get("day_ago") else None
            week_pct = ((current / prices["week_ago"] - 1) * 100) if prices.get("week_ago") else None
            month_pct = ((current / prices["month_ago"] - 1) * 100) if prices.get("month_ago") else None

            report.append(
                f"| {ticker} | {price_str} | {fmt_pct(day_pct)} | {fmt_pct(week_pct)} | {fmt_pct(month_pct)} |"
            )

    report.append("")

    # --- Noticias ---
    report.append("## 📰 Destaques do Mercado\n")
    if news:
        for n in news:
            report.append(f"  - [{n['title']}]({n['link']}) — _{n['source']}_")
        report.append("")
    else:
        report.append("  Nenhuma notícia encontrada.\n")

    # --- Noticias Macro ---
    report.append("\n## 🌎 Cenário Macro — Notícias\n")
    if macro_news:
        for n in macro_news:
            report.append(f"  - [{n['title']}]({n['link']}) — _{n['source']}_")
        report.append("")
    else:
        report.append("  Nenhuma notícia macro relevante.\n")

    # --- Insights ---
    report.append("## 💡 Insights & Recomendações\n")
    for insight in insights:
        report.append(f"  {insight}")
    report.append("")

    report.append(f"\n---\n*Relatório gerado em {date_str}*")

    # 7. Salvar
    REPORTS_DIR.mkdir(exist_ok=True)
    filename = REPORTS_DIR / f"daily_{file_date}.md"
    content = "\n".join(report)
    with open(filename, "w") as f:
        f.write(content)
    print(f"\n✅ Relatório salvo: {filename}")

    if print_stdout:
        print("\n" + content)


if __name__ == "__main__":
    main()
