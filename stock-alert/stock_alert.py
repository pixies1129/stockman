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

NEWS_TICKERS = ["^GSPC", "^NDX", "TSLA", "005930.KS", "000660.KS"]


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


def collect_news() -> list[dict]:
    """yfinance에서 최신 뉴스 수집 (무료, API 불필요)"""
    seen = set()
    items = []
    for sym in NEWS_TICKERS:
        try:
            raw = yf.Ticker(sym).news or []
            for item in raw[:6]:
                content = item.get("content", item)
                title = content.get("title", "")
                publisher = (
                    content.get("provider", {}).get("displayName", "")
                    or content.get("publisher", "")
                )
                if title and title not in seen:
                    seen.add(title)
                    items.append({"title": title, "publisher": publisher})
        except Exception as e:
            print(f"  [{sym}] 뉴스 수집 실패: {e}")
    print(f"  수집된 뉴스: {len(items)}건")
    return items[:8]


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


def build_message(stock_data: dict, news_items: list[dict]) -> str:
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


def main():
    print(f"=== 증시 알리미 시작 ({datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}) ===")

    print("\n[1] 주가 데이터 수집 중...")
    stock_data = {}
    for name, info in STOCKS.items():
        data = get_stock_data(name, info)
        stock_data[name] = data
        if data:
            print(f"  ✓ {name}: {format_price(data)} ({data['change_pct']:+.2f}%)")

    print("\n[2] 뉴스 수집 중...")
    news_items = collect_news()

    message = build_message(stock_data, news_items)
    print(f"\n[3] 메시지 구성 완료 ({len(message)}자)")

    print("\n[4] 텔레그램 전송 중...")
    success = send_telegram_message(message)
    if success:
        print("  ✓ 텔레그램 전송 성공!")
    else:
        print("  ✗ 텔레그램 전송 실패")
        exit(1)


if __name__ == "__main__":
    main()
