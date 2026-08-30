import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "latest.json"


def get_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "StockCardWeb/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo_chart(symbol):
    q = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval=1m&range=1d"
    data = get_json(url)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if price is not None and prev not in (None, 0):
        change_pct = (float(price) / float(prev) - 1.0) * 100.0
    return price, change_pct, meta.get("regularMarketTime")


def krx_gold(errors):
    key = os.getenv("KRX_AUTH_KEY", "").strip()
    if not key:
        return {"symbol":"GOLD_1G","name":"KRX 금 1g","value":None,"change_pct":None,"unit":"₩","source":"WAITING_KRX_SECRET","market_state":"WAITING"}
    # KRX OpenAPI daily gold endpoint used by the existing project.
    # Do not expose the key to the browser; it is sent only from GitHub Actions.
    url = "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd"
    headers = {"AUTH_KEY": key, "User-Agent": "StockCardWeb/1.0"}
    try:
        data = get_json(url, headers=headers)
        rows = data.get("OutBlock_1") or data.get("output") or data.get("data") or []
        target = None
        for row in rows:
            code = str(row.get("ISU_CD") or row.get("ISU_SRT_CD") or row.get("MKT_ID") or "")
            name = str(row.get("ISU_NM") or row.get("ITEM_NM") or "")
            if code == "04020000" or "금 99.99_1kg" in name:
                target = row
                break
        if not target and rows:
            target = rows[0]
        if target:
            raw = target.get("TDD_CLSPRC") or target.get("CLSPRC") or target.get("CLOSE_PRICE")
            value = float(str(raw).replace(",", "")) if raw not in (None, "") else None
            chg = target.get("FLUC_RT") or target.get("CMPPREVDD_PRC")
            try:
                chg = float(str(chg).replace(",", ""))
            except Exception:
                chg = None
            return {"symbol":"GOLD_1G","name":"KRX 금 1g","value":value,"change_pct":chg,"unit":"₩","source":"KRX","market_state":"DAILY"}
        errors.append("KRX gold: no rows")
    except Exception as e:
        errors.append(f"KRX gold: {e!r}")
    return {"symbol":"GOLD_1G","name":"KRX 금 1g","value":None,"change_pct":None,"unit":"₩","source":"KRX_ERROR","market_state":"ERROR"}


def extract_holdings_generic(obj):
    # Endpoint/response shapes differ by Toss service. This adapter intentionally
    # accepts common field names but never guesses an endpoint URL.
    rows = None
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        for k in ("holdings", "positions", "items", "data", "output", "stocks"):
            v = obj.get(k)
            if isinstance(v, list):
                rows = v
                break
            if isinstance(v, dict):
                for kk in ("items", "holdings", "positions", "stocks"):
                    if isinstance(v.get(kk), list):
                        rows = v.get(kk)
                        break
            if rows is not None:
                break
    if not rows:
        return []

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        symbol = r.get("symbol") or r.get("stockCode") or r.get("code") or r.get("ticker") or r.get("isuCd")
        name = r.get("name") or r.get("stockName") or r.get("securityName") or symbol
        qty = r.get("quantity") or r.get("qty") or r.get("holdingQty") or r.get("balanceQty")
        avg = r.get("avg_price") or r.get("avgPrice") or r.get("averagePrice") or r.get("purchasePrice")
        price = r.get("price") or r.get("currentPrice") or r.get("lastPrice") or r.get("marketPrice")
        market = r.get("market") or ("KR" if symbol and str(symbol).isdigit() else "US")
        currency = r.get("currency") or ("KRW" if market == "KR" else "USD")
        try: qty = float(str(qty).replace(",", "")) if qty not in (None, "") else 0.0
        except Exception: qty = 0.0
        try: avg = float(str(avg).replace(",", "")) if avg not in (None, "") else None
        except Exception: avg = None
        try: price = float(str(price).replace(",", "")) if price not in (None, "") else None
        except Exception: price = None
        if not symbol or qty <= 0:
            continue
        ret = ((price / avg) - 1.0) * 100.0 if price is not None and avg not in (None, 0) else None
        pnl = ((price - avg) * qty) if price is not None and avg is not None else None
        out.append({
            "symbol": str(symbol), "name": str(name or symbol), "market": market, "currency": currency,
            "price": price, "avg_price": avg, "quantity": qty, "return_pct": ret, "pnl": pnl,
            "source": "TOSS"
        })
    return out


def toss_holdings(errors):
    url = os.getenv("TOSS_HOLDINGS_URL", "").strip()
    if not url:
        errors.append("TOSS_HOLDINGS_URL secret not configured")
        return []

    client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
    client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
    account_seq = os.getenv("TOSS_ACCOUNT_SEQ", "").strip()
    token = os.getenv("TOSS_ACCESS_TOKEN", "").strip()

    headers = {"User-Agent": "StockCardWeb/1.0", "Accept": "application/json"}
    # Keep authentication server-side. Exact Toss header names can be overridden
    # with secret values if the user's working endpoint expects them.
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if client_id:
        headers[os.getenv("TOSS_CLIENT_ID_HEADER", "x-client-id")] = client_id
    if client_secret:
        headers[os.getenv("TOSS_CLIENT_SECRET_HEADER", "x-client-secret")] = client_secret
    if account_seq:
        headers[os.getenv("TOSS_ACCOUNT_SEQ_HEADER", "x-account-seq")] = account_seq

    try:
        data = get_json(url, headers=headers)
        rows = extract_holdings_generic(data)
        if not rows:
            errors.append("Toss holdings endpoint returned no recognizable holdings rows")
        return rows
    except Exception as e:
        errors.append(f"Toss holdings: {e!r}")
        return []


def main():
    errors = []
    portfolio = toss_holdings(errors)

    market = []
    market.append(krx_gold(errors))
    yahoo_specs = [
        ("USDKRW", "원/달러", "KRW=X", "₩"),
        ("DXY", "달러지수", "DX-Y.NYB", ""),
        ("SOX", "필라델피아반도체", "^SOX", ""),
    ]
    for symbol, name, provider, unit in yahoo_specs:
        try:
            q = yahoo_chart(provider)
            if q:
                value, chg, provider_time = q
                market.append({"symbol":symbol,"name":name,"value":value,"change_pct":chg,"unit":unit,"source":"YAHOO_FINANCE","market_state":"LIVE_OR_LAST","provider_time":provider_time})
            else:
                raise RuntimeError("no result")
        except Exception as e:
            errors.append(f"{symbol}: {e!r}")
            market.append({"symbol":symbol,"name":name,"value":None,"change_pct":None,"unit":unit,"source":"ERROR","market_state":"ERROR"})

    # US2Y and night futures are kept as explicit placeholders until a selected provider is configured.
    market.append({"symbol":"US2Y","name":"미국 2년물","value":None,"change_pct":None,"unit":"%","source":"PROVIDER_NOT_CONFIGURED","market_state":"WAITING"})
    market.append({"symbol":"KOSPI200_NIGHT","name":"KOSPI200 야간선물","value":None,"change_pct":None,"unit":"","source":"PROVIDER_NOT_CONFIGURED","market_state":"WAITING"})

    mode = "LIVE" if portfolio or any(x.get("value") is not None for x in market) else "MOCK"
    payload = {"ok": not errors, "mode": mode, "updated_at": time.time(), "portfolio": portfolio, "market": market, "errors": errors}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": mode, "portfolio": len(portfolio), "market": len(market), "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
