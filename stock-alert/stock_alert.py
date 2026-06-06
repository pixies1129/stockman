#!/usr/bin/env python3
"""
매일 오전 8시 텔레그램으로 증시 현황 + 뉴스를 전송하는 스크립트
GitHub Actions에서 실행됨
"""

import os
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

BLS_API_URL  = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

STOCKS = {
    "삼성전자": {"ticker": "005930.KS", "currency": "KRW"},
    "SK하이닉스": {"ticker": "000660.KS", "currency": "KRW"},
    "Tesla": {"ticker": "TSLA", "currency": "USD"},
    "S&P 500": {"ticker": "^GSPC", "currency": "USD"},
    "나스닥 100": {"ticker": "^NDX", "currency": "USD"},
    "다우존스": {"ticker": "^DJI", "currency": "USD"},
}

NEWS_TICKERS = ["^GSPC", "^NDX", "TSLA", "005930.KS", "000660.KS"]

BLS_SERIES = {
    "CUUR0000SA0":    "cpi",         # CPI-U 전체 (지수)
    "CUUR0000SA0L1E": "core_cpi",    # 근원 CPI (지수)
    "LNS14000000":    "unemployment", # 실업률 (%)
    "CES0000000001":  "nfp",         # 비농업 취업자수 (천명)
}


# ── 번역 ──────────────────────────────────────────────────────────────────────

def translate_to_korean(text: str) -> str:
    """MyMemory API로 영문 → 한글 번역 (API 키 불필요, 클라우드 IP 허용)"""
    if any("가" <= c <= "힣" for c in text):
        return text  # 이미 한글이면 건너뜀
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ko"},
            timeout=8,
        )
        if resp.ok:
            data = resp.json()
            if data.get("responseStatus") == 200:
                translated = data["responseData"]["translatedText"]
                if translated and translated.strip():
                    return translated
    except Exception as e:
        print(f"  번역 실패 ({text[:30]}...): {e}")
    return text


# ── 경제지표 ──────────────────────────────────────────────────────────────────

def get_bls_economic_data() -> dict:
    """BLS 공개 API로 CPI·실업률·NFP 수집 (API 키 불필요)"""
    now = datetime.now(KST)
    try:
        resp = requests.post(
            BLS_API_URL,
            json={
                "seriesid": list(BLS_SERIES.keys()),
                "startyear": str(now.year - 1),
                "endyear":   str(now.year),
            },
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        print(f"  BLS HTTP {resp.status_code}")
        if not resp.ok:
            print(f"  BLS 오류 내용: {resp.text[:300]}")
            return {}

        payload = resp.json()
        status  = payload.get("status", "")
        print(f"  BLS status: {status}")
        if status != "REQUEST_SUCCEEDED":
            print(f"  BLS message: {payload.get('message', [])}")
            return {}

        result = {}
        for series in payload.get("Results", {}).get("series", []):
            sid = series["seriesID"]
            key = BLS_SERIES.get(sid)
            if not key:
                continue

            items = sorted(
                [d for d in series["data"]
                 if d.get("period", "M00").startswith("M") and d["period"] != "M13"],
                key=lambda x: (x["year"], x["period"]),
                reverse=True,
            )
            if not items:
                print(f"  {sid}: 데이터 없음")
                continue

            latest     = items[0]
            date_label = f"{latest['year']}-{latest['period'][1:]}-01"
            val        = float(latest["value"])

            if key in ("cpi", "core_cpi"):
                if len(items) >= 13:
                    yoy = (val - float(items[12]["value"])) / float(items[12]["value"]) * 100
                    result[f"{key}_yoy"] = {"value": yoy, "date": date_label}
                    print(f"  ✓ {key}_yoy: {yoy:+.2f}% ({date_label})")
                else:
                    print(f"  {key}: 데이터 부족 ({len(items)}개)")
            elif key == "unemployment":
                result["unemployment"] = {"value": val, "date": date_label}
                print(f"  ✓ unemployment: {val}% ({date_label})")
            elif key == "nfp":
                if len(items) >= 2:
                    change = val - float(items[1]["value"])
                    result["nfp_change"] = {"value": change, "date": date_label}
                    print(f"  ✓ nfp_change: {change:+,.0f}천명 ({date_label})")

        return result
    except Exception as e:
        print(f"  BLS 수집 실패: {e}")
        return {}


def get_rates() -> dict:
    """yfinance로 미 10년물 국채 수집 + FRED 키 있으면 기준금리 추가"""
    result = {}

    # 미 10년물 국채 수익률 (API 키 불필요)
    try:
        hist = yf.Ticker("^TNX").history(period="5d")
        if not hist.empty:
            val  = float(hist["Close"].iloc[-1])
            date = hist.index[-1].strftime("%Y-%m-%d")
            result["treasury_10y"] = {"value": val, "date": date}
            print(f"  ✓ 10년물 국채: {val:.2f}% ({date})")
    except Exception as e:
        print(f"  10년물 국채 수집 실패: {e}")

    # 연방기금금리 (FRED_API_KEY 설정 시에만)
    api_key = os.environ.get("FRED_API_KEY", "")
    if api_key:
        try:
            resp = requests.get(
                FRED_API_URL,
                params={"series_id": "FEDFUNDS", "api_key": api_key,
                        "file_type": "json", "sort_order": "desc", "limit": 5},
                timeout=10,
            )
            if resp.ok:
                for obs in resp.json().get("observations", []):
                    if obs.get("value") not in (".", None, ""):
                        val = float(obs["value"])
                        result["fed_rate"] = {"value": val, "date": obs["date"]}
                        print(f"  ✓ fed_rate: {val:.2f}% ({obs['date']})")
                        break
        except Exception as e:
            print(f"  FRED 수집 실패: {e}")

    return result


def get_economic_indicators() -> dict:
    result = get_bls_economic_data()
    result.update(get_rates())
    return result


def format_econ_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.year}년 {dt.month:02d}월"
    except Exception:
        return date_str


def build_economic_section(econ: dict) -> str:
    lines = ["", "─" * 22, "🇺🇸 미국 주요 경제지표", ""]

    # 물가지표
    lines.append("📊 물가지표")
    cpi  = econ.get("cpi_yoy")
    core = econ.get("core_cpi_yoy")
    if cpi or core:
        if cpi:
            arrow = "📈" if cpi["value"] > 0 else "📉"
            lines.append(f"  {arrow} CPI (전년비): {cpi['value']:+.1f}% ({format_econ_date(cpi['date'])})")
        if core:
            arrow = "📈" if core["value"] > 0 else "📉"
            lines.append(f"  {arrow} 근원 CPI (전년비): {core['value']:+.1f}% ({format_econ_date(core['date'])})")
    else:
        lines.append("  데이터 수집 실패")

    # 고용지표
    lines.append("")
    lines.append("👷 고용지표")
    ue  = econ.get("unemployment")
    nfp = econ.get("nfp_change")
    if ue or nfp:
        if ue:
            lines.append(f"  실업률: {ue['value']:.1f}% ({format_econ_date(ue['date'])})")
        if nfp:
            sign = "+" if nfp["value"] >= 0 else ""
            lines.append(f"  비농업 취업자 변화: {sign}{nfp['value']:,.0f}천명 ({format_econ_date(nfp['date'])})")
    else:
        lines.append("  데이터 수집 실패")

    # 연준
    lines.append("")
    lines.append("🏦 연준 (Fed)")
    fed = econ.get("fed_rate")
    t10 = econ.get("treasury_10y")
    if fed:
        lines.append(f"  기준금리 (EFFR): {fed['value']:.2f}% ({format_econ_date(fed['date'])})")
    if t10:
        lines.append(f"  미 10년물 국채: {t10['value']:.2f}% ({format_econ_date(t10['date'])})")
    if not fed and not t10:
        lines.append("  데이터 수집 실패")

    return "\n".join(lines)


# ── 주가 ──────────────────────────────────────────────────────────────────────

def get_stock_data(name: str, info: dict) -> dict | None:
    try:
        ticker = yf.Ticker(info["ticker"])
        hist   = ticker.history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        current    = float(hist["Close"].iloc[-1])
        prev       = float(hist["Close"].iloc[-2])
        change     = current - prev
        change_pct = (change / prev) * 100
        return {"price": current, "change": change, "change_pct": change_pct, "currency": info["currency"]}
    except Exception as e:
        print(f"  [{name}] 데이터 수집 실패: {e}")
        return None


def format_price(data: dict) -> str:
    if data["currency"] == "KRW":
        return f"{data['price']:,.0f}원"
    return f"${data['price']:,.2f}"


# ── 뉴스 ──────────────────────────────────────────────────────────────────────

def collect_news() -> list[dict]:
    """yfinance에서 뉴스 수집 후 MyMemory로 한글 번역"""
    seen  = set()
    items = []
    for sym in NEWS_TICKERS:
        try:
            raw = yf.Ticker(sym).news or []
            for item in raw[:6]:
                content   = item.get("content", item)
                title_raw = content.get("title", "")
                publisher = (
                    content.get("provider", {}).get("displayName", "")
                    or content.get("publisher", "")
                )
                if title_raw and title_raw not in seen:
                    seen.add(title_raw)
                    title_ko = translate_to_korean(title_raw)
                    items.append({"title": title_ko, "publisher": publisher})
        except Exception as e:
            print(f"  [{sym}] 뉴스 수집 실패: {e}")
    print(f"  수집된 뉴스: {len(items)}건")
    return items[:8]


# ── 텔레그램 ──────────────────────────────────────────────────────────────────

def send_telegram_message(text: str) -> bool:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id   = os.environ["TELEGRAM_CHAT_ID"]
    if len(text) > 4000:
        text = text[:3990] + "...\n[메시지 길이 초과로 잘림]"
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    if not resp.ok:
        print(f"텔레그램 전송 실패: {resp.status_code} {resp.text}")
        return False
    return True


# ── 메시지 조립 ───────────────────────────────────────────────────────────────

def build_message(stock_data: dict, news_items: list[dict], econ: dict) -> str:
    day_map  = {"Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목",
                "Fri": "금", "Sat": "토", "Sun": "일"}
    now      = datetime.now(KST)
    date_str = now.strftime(f"%Y년 %m월 %d일 ({day_map.get(now.strftime('%a'), '')})")

    lines = [f"📊 {date_str} 증시 현황", ""]

    lines.append("🇰🇷 국내")
    for name in ["삼성전자", "SK하이닉스"]:
        data = stock_data.get(name)
        if data:
            arrow = "📈" if data["change_pct"] > 0 else "📉" if data["change_pct"] < 0 else "➡️"
            lines.append(f"{arrow} {name}: {format_price(data)} ({data['change_pct']:+.2f}%)")
        else:
            lines.append(f"❓ {name}: 데이터 없음")

    lines.append("")
    lines.append("🌍 글로벌")
    for name in ["S&P 500", "나스닥 100", "다우존스", "Tesla"]:
        data = stock_data.get(name)
        if data:
            arrow = "📈" if data["change_pct"] > 0 else "📉" if data["change_pct"] < 0 else "➡️"
            lines.append(f"{arrow} {name}: {format_price(data)} ({data['change_pct']:+.2f}%)")
        else:
            lines.append(f"❓ {name}: 데이터 없음")

    lines.append("")
    lines.append("🚀 스페이스X: 미상장")

    lines.append(build_economic_section(econ))

    lines.append("")
    lines.append("─" * 22)
    lines.append("📰 오늘의 주요 뉴스")
    lines.append("")

    numbers = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"]
    if news_items:
        for i, item in enumerate(news_items):
            num = numbers[i] if i < len(numbers) else f"{i+1}."
            pub = f" ({item['publisher']})" if item["publisher"] else ""
            lines.append(f"{num} {item['title']}{pub}")
    else:
        lines.append("뉴스를 가져오지 못했습니다.")

    return "\n".join(lines)


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main():
    print(f"=== 증시 알리미 시작 ({datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}) ===")

    print("\n[1] 주가 데이터 수집 중...")
    stock_data = {}
    for name, info in STOCKS.items():
        data = get_stock_data(name, info)
        stock_data[name] = data
        if data:
            print(f"  ✓ {name}: {format_price(data)} ({data['change_pct']:+.2f}%)")

    print("\n[2] 경제지표 수집 중...")
    econ = get_economic_indicators()

    print("\n[3] 뉴스 수집 및 번역 중...")
    news_items = collect_news()

    message = build_message(stock_data, news_items, econ)
    print(f"\n[4] 메시지 구성 완료 ({len(message)}자)")

    print("\n[5] 텔레그램 전송 중...")
    success = send_telegram_message(message)
    if success:
        print("  ✓ 텔레그램 전송 성공!")
    else:
        print("  ✗ 텔레그램 전송 실패")
        exit(1)


if __name__ == "__main__":
    main()
