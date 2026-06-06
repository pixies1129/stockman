#!/usr/bin/env python3
"""
매일 오전 8시 텔레그램으로 증시 현황 + AI 분석을 전송하는 스크립트
GitHub Actions에서 실행됨
"""

import os
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
import anthropic

KST = timezone(timedelta(hours=9))

STOCKS = {
    "삼성전자": {"ticker": "005930.KS", "currency": "KRW"},
    "SK하이닉스": {"ticker": "000660.KS", "currency": "KRW"},
    "Tesla": {"ticker": "TSLA", "currency": "USD"},
    "S&P 500": {"ticker": "^GSPC", "currency": "USD"},
    "나스닥 100": {"ticker": "^NDX", "currency": "USD"},
    "다우존스": {"ticker": "^DJI", "currency": "USD"},
}


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


def analyze_with_claude(stock_lines: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")

    prompt = f"""오늘({today}) 주요 증시 현황:
{stock_lines}

웹 검색으로 오늘자 글로벌 경제·증시 관련 뉴스를 5개 이상 수집한 뒤, 아래 형식으로 한국어로 작성해주세요.

【오늘의 주요 경제 뉴스】

① [뉴스 제목] (출처·날짜)
→ 한 줄 요약

② [뉴스 제목] (출처·날짜)
→ 한 줄 요약

(③~⑤ 동일 형식, 총 5개 이상)

【종합 시사점】
수집한 뉴스를 바탕으로 오늘 시장에 미치는 영향과 투자자가 주목할 점을 3줄 이내로 정리.

규칙: 추측 없이 실제 뉴스만 인용. 스페이스X IPO 뉴스가 있으면 포함."""

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=3000,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        result_text = "".join(block.text for block in response.content if block.type == "text")
        return result_text.strip() or "뉴스를 가져오지 못했습니다."
    except Exception as e:
        print(f"Claude 뉴스 수집 실패: {e}")
        return f"뉴스 수집 오류: {e}"


def send_telegram_message(text: str) -> bool:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # 텔레그램 메시지 최대 4096자
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
    day_en = now.strftime("%a")
    date_str = now.strftime(f"%Y년 %m월 %d일 ({day_map.get(day_en, day_en)})")

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
    lines.append("🚀 스페이스X: 미상장 (AI 분석에 IPO 뉴스 포함)")
    lines.append("")
    lines.append("─" * 22)
    lines.append("🤖 AI 분석")
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

    print("\n[2] Claude AI 분석 중 (웹 검색 포함)...")
    stock_lines = "\n".join(
        f"- {name}: {format_price(d)} ({d['change_pct']:+.2f}%)"
        for name, d in stock_data.items() if d
    )
    analysis = analyze_with_claude(stock_lines)
    print(f"  ✓ 분석 완료 ({len(analysis)}자)")

    message = build_message(stock_data, analysis)
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
