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

STOCKS = {
    "삼성전자": {"ticker": "005930.KS", "currency": "KRW"},
    "SK하이닉스": {"ticker": "000660.KS", "currency": "KRW"},
    "Tesla": {"ticker": "TSLA", "currency": "USD"},
    "S&P 500": {"ticker": "^GSPC", "currency": "USD"},
    "나스닥 100": {"ticker": "^NDX", "currency": "USD"},
    "다우존스": {"ticker": "^DJI", "currency": "USD"},
}

NEWS_TICKERS = ["^GSPC", "TSLA", "005930.KS", "000660.KS", "^NDX"]


def get_stock_data(name: str, info: dict) -> dict | None:
    try:
        ticker = yf.Ticker(info["ticker"])
        hist = ticker.history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        change = current - prev
        change_pct = (change / prev) * 100
        return {"price": current, "change": change, "change_pct": change_pct, "currency": info["currency"]}
    except Exception as e:
        print(f"  [{name}] 데이터 수집 실패: {e}")
        return None


def format_price(data: dict) -> str:
    if data["currency"] == "KRW":
        return f"{data['price']:,.0f}원"
    return f"${data['price']:,.2f}"


def collect_news() -> str:
    """yfinance에서 뉴스 수집 (무료, API 불필요)"""
    seen = set()
    lines = []
    for sym in NEWS_TICKERS:
        try:
            raw = yf.Ticker(sym).news or []
            for item in raw[:5]:
                content = item.get("content", item)
                title = content.get("title", "")
                publisher = (
                    content.get("provider", {}).get("displayName", "")
                    or content.get("publisher", "")
                )
                if title and title not in seen:
                    seen.add(title)
                    lines.append(f"- {title} ({publisher})" if publisher else f"- {title}")
        except Exception as e:
            print(f"  [{sym}] 뉴스 수집 실패: {e}")
    print(f"  수집된 뉴스: {len(lines)}건")
    return "\n".join(lines[:15])


def summarize_with_gemini(news_text: str, stock_lines: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "오류: GEMINI_API_KEY가 설정되지 않았습니다."

    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    prompt = f"""오늘({today}) 수집된 글로벌 증시 뉴스:
{news_text}

오늘 증시 현황:
{stock_lines}

위 뉴스와 증시 데이터를 바탕으로 한국어로 아래 형식에 맞게 작성해주세요.

【오늘의 주요 경제 뉴스】

① [뉴스 제목] (출처)
→ 한 줄 요약 (한국어)

② [뉴스 제목] (출처)
→ 한 줄 요약

(③~⑤ 동일, 총 5개)

【종합 시사점】
오늘 시장 흐름과 투자자가 주목할 점을 3줄 이내로."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(url, json=payload, timeout=60)
        if not resp.ok:
            print(f"Gemini API 오류: {resp.status_code}")
            print(f"응답: {resp.text[:500]}")
            return f"요약 오류: HTTP {resp.status_code}"
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini 요약 실패: {e}")
        return f"요약 오류: {e}"


def send_telegram_message(text: str) -> bool:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

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


def build_message(stock_data: dict, analysis: str) -> str:
    day_map = {"Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목", "Fri": "금", "Sat": "토", "Sun": "일"}
    now = datetime.now(KST)
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
    lines.append("")
    lines.append("─" * 22)
    lines.append("🔍 오늘의 경제 뉴스")
    lines.append("")
    lines.append(analysis)

    return "\n".join(lines)


def main():
    print(f"=== 증시 알리미 시작 ({datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}) ===")

    print("\n[1] 주가 데이터 수집 중...")
    stock_data = {}
    for name, info in STOCKS.items():
        data = get_stock_data(name, info)
        stock_data[name] = data
        if data:
            print(f"  ✓ {name}: {format_price(data)} ({data['change_pct']:+.2f}%)")

    print("\n[2] 뉴스 수집 중 (yfinance)...")
    news_text = collect_news()

    print("\n[3] Gemini로 한국어 요약 중...")
    stock_lines = "\n".join(
        f"- {name}: {format_price(d)} ({d['change_pct']:+.2f}%)"
        for name, d in stock_data.items() if d
    )
    analysis = summarize_with_gemini(news_text, stock_lines)
    print(f"  ✓ 요약 완료 ({len(analysis)}자)")

    message = build_message(stock_data, analysis)
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
