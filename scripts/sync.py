#!/usr/bin/env python3
"""sync.py — Sincroniza precos entre yfinance/CoinGecko e Google Sheets via Composio.

Uso:
    sync.py snapshot   Tira foto dos tickers atuais da planilha -> snapshot.json
    sync.py check      Compara planilha vs snapshot, mostra diff
    sync.py update     Atualiza coluna C (preco atual) de cada ticker
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent  # scripts/ → raiz do repo
ENV_FILE = PROJECT_DIR / ".env"
SHEETS_FILE = PROJECT_DIR / "sheets.json"
SNAPSHOT_FILE = PROJECT_DIR / "snapshot.json"

# Linhas que sao categorias, nao tickers
SKIP_LABELS = {
    "Ações BR", "Ações", "RF", "Caixa", "Pre", "Inflacao",
    "FIIs", "Equity", "Proteções", "Ações BR",
}

load_dotenv(ENV_FILE)
SPREADSHEET_ID = os.environ["INVEST_SPREADSHEET_ID"]
SHEET_WHITELIST = set(
    s.strip() for s in os.environ.get("SHEET_WHITELIST", "").split(",") if s.strip()
)


def col_letter(n: int) -> str:
    """Converte indice de coluna (1=A) para letra (ex: 29=AC)."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def composio(action: str, payload: dict) -> dict:
    """Chama composio execute e retorna o JSON parseado."""
    composio_bin = os.path.expanduser("~/.composio/composio")
    cmd = [composio_bin, "execute", action, "-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"composio failed: {result.stderr[:500]}")
    data = json.loads(result.stdout)
    if not data.get("successful"):
        raise RuntimeError(f"composio error: {data.get('error', 'unknown')}")
    return data


def load_sheets_config() -> dict:
    with open(SHEETS_FILE) as f:
        return json.load(f)


def load_snapshot() -> dict | None:
    if SNAPSHOT_FILE.exists():
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return None


def save_snapshot(data: dict):
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def scan_sheet(sheet_name: str, ticker_start_row: int) -> list[dict]:
    """Le a planilha e retorna lista de {row, ticker, price_col_letter}."""
    # Le em batches de 50 linhas
    tickers = []
    row = ticker_start_row
    while row < ticker_start_row + 200:  # max ~200 linhas de scan
        end = min(row + 49, row + 199)
        range_str = f"{sheet_name}!A{row}:C{end}"
        data = composio("GOOGLESHEETS_BATCH_GET", {
            "spreadsheet_id": SPREADSHEET_ID,
            "ranges": [range_str],
        })
        values = data["data"]["valueRanges"][0].get("values", [])

        for i, cols in enumerate(values):
            actual_row = row + i
            if not cols or not cols[0] or not str(cols[0]).strip():
                continue
            label = str(cols[0]).strip()
            if label in SKIP_LABELS:
                continue
            # E um ticker?
            if not any(c.isalpha() for c in label) or ":" not in label and not label[0].isalpha():
                continue
            tickers.append({
                "row": actual_row,
                "ticker": label,
                "current_price": cols[2] if len(cols) > 2 else "",
            })

        if len(values) < 50:
            break  # fim da aba
        row += 50

    return tickers


def cmd_snapshot():
    """Tira foto de todas as abas -> snapshot.json"""
    config = load_sheets_config()
    ss = config["spreadsheets"][SPREADSHEET_ID]
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spreadsheet_id": SPREADSHEET_ID,
        "sheets": {},
    }
    for sheet_name, cfg in ss["sheets"].items():
        if SHEET_WHITELIST and sheet_name not in SHEET_WHITELIST:
            continue
        tickers = scan_sheet(sheet_name, cfg["ticker_start_row"])
        snapshot["sheets"][sheet_name] = {
            "tickers": [t["ticker"] for t in tickers],
            "positions": {t["ticker"]: {"row": t["row"]} for t in tickers},
        }
        print(f"  {sheet_name}: {len(tickers)} tickers")

    save_snapshot(snapshot)
    print(f"✅ Snapshot salvo: {len(snapshot['sheets'])} abas")


def cmd_check() -> bool:
    """Compara planilha atual vs snapshot. Retorna True se OK."""
    snapshot = load_snapshot()
    if not snapshot:
        print("❌ Nenhum snapshot encontrado. Rode 'sync.py snapshot' primeiro.")
        return False

    config = load_sheets_config()
    ss = config["spreadsheets"][SPREADSHEET_ID]
    changed = False

    for sheet_name, snap_data in snapshot["sheets"].items():
        cfg = ss["sheets"].get(sheet_name)
        if not cfg:
            print(f"⚠️  Aba '{sheet_name}' nao esta no sheets.json")
            continue

        current = scan_sheet(sheet_name, cfg["ticker_start_row"])
        current_tickers = {t["ticker"]: t for t in current}
        snap_tickers = set(snap_data["tickers"])

        added = set(current_tickers) - snap_tickers
        removed = snap_tickers - set(current_tickers)
        moved = []
        for tkr in snap_tickers & set(current_tickers):
            if current_tickers[tkr]["row"] != snap_data["positions"][tkr]["row"]:
                moved.append(tkr)

        if added or removed or moved:
            changed = True
            print(f"\n📋 {sheet_name}:")
            for t in sorted(added):
                print(f"  + {t} (nova linha {current_tickers[t]['row']})")
            for t in sorted(removed):
                print(f"  - {t} (removido)")
            for t in sorted(moved):
                old = snap_data["positions"][t]["row"]
                new = current_tickers[t]["row"]
                print(f"  ~ {t} (linha {old} → {new})")

    if changed:
        print("\n❌ Planilha mudou. Rode 'sync.py snapshot' para atualizar o snapshot.")
        return False
    else:
        print("✅ Nenhuma mudanca detectada.")
        return True


def resolve_ticker(sheet_ticker: str, ticker_map: dict) -> tuple[str, str]:
    """Retorna (source, symbol). source = 'yfinance' ou 'coingecko'."""
    mapped = ticker_map.get(sheet_ticker, sheet_ticker)
    if mapped.startswith("COINGECKO:"):
        return "coingecko", mapped.split(":", 1)[1]  # ex: "BTC/BRL"
    return "yfinance", mapped


def fetch_price_yfinance(symbol: str) -> float | None:
    """Busca ultimo preco no yfinance."""
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        return info.get("lastPrice") or info.get("regularMarketPreviousClose") or info.get("previousClose")
    except Exception as e:
        print(f"  ⚠️  yfinance {symbol}: {e}")
        return None


def fetch_price_coingecko(pair: str) -> float | None:
    """Busca preco BTC/BRL na CoinGecko (gratuito, sem API key)."""
    import urllib.request

    coin_map = {"BTC/BRL": ("bitcoin", "brl"), "BTC/USD": ("bitcoin", "usd")}
    coin_id, vs_currency = coin_map.get(pair, (None, None))
    if not coin_id:
        print(f"  ⚠️  CoinGecko: par desconhecido {pair}")
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={vs_currency}"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        return resp[coin_id][vs_currency]
    except Exception as e:
        print(f"  ⚠️  CoinGecko {pair}: {e}")
        return None


def cmd_update():
    """Atualiza precos na aba separada (PRICE_SHEET)."""
    if not cmd_check():
        print("\n❌ Abortado. Atualize o snapshot primeiro.")
        sys.exit(1)

    config = load_sheets_config()
    ticker_map = config["ticker_map"]
    snapshot = load_snapshot()
    assert snapshot is not None, "snapshot required after cmd_check"

    price_sheet = os.environ.get("PRICE_SHEET", "AtivosPrecos")

    # Coleta todos os tickers e precos
    rows = [["Ticker", "Preço", "Moeda"]]  # cabecalho
    updated = 0
    for sheet_name, snap_data in snapshot["sheets"].items():
        for ticker in snap_data["tickers"]:
            source, symbol = resolve_ticker(ticker, ticker_map)

            if source == "yfinance":
                price = fetch_price_yfinance(symbol)
            else:
                price = fetch_price_coingecko(symbol)

            if price is None:
                continue

            # Determina moeda
            is_us = any(prefix in ticker for prefix in ["NASDAQ:", "NYSEARCA:"])
            is_btc = ticker in ("CURRENCY:BTCBRL", "BTCUSD")
            currency = "USD" if (is_us or (is_btc and ticker == "BTCUSD")) else "BRL"

            rows.append([ticker, price, currency])
            print(f"  {ticker}: {price:.2f} {currency}")
            updated += 1

    if not updated:
        print("⚠️  Nenhum preco obtido.")
        return

    # Escreve na aba separada (sem mexer nas abas originais)
    print(f"\n📤 Escrevendo {updated} precos em '{price_sheet}'...")
    composio("GOOGLESHEETS_BATCH_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "sheet_name": price_sheet,
        "values": rows,
    })

    print(f"✅ {updated} precos atualizados em '{price_sheet}'")
    print("📸 Atualizando snapshot...")
    cmd_snapshot()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: sync.py [snapshot|check|update]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "snapshot":
        cmd_snapshot()
    elif cmd == "check":
        ok = cmd_check()
        sys.exit(0 if ok else 1)
    elif cmd == "update":
        cmd_update()
    else:
        print(f"Comando desconhecido: {cmd}")
        sys.exit(1)
