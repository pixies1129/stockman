#!/usr/bin/env python3
"""
텔레그램 봇 토큰 & 채팅 ID 발급 도우미 (로컬에서 1회만 실행)
"""

import requests

print("=" * 50)
print("  텔레그램 봇 설정 도우미")
print("=" * 50)
print()
print("📋 사전 준비:")
print("  1. 텔레그램 앱에서 @BotFather 검색 후 대화 시작")
print("  2. /newbot 입력")
print("  3. 봇 이름 입력 (예: 증시알리미)")
print("  4. 봇 사용자명 입력 (예: mystock_alert_bot)  ← 영문+숫자, bot으로 끝나야 함")
print("  5. BotFather가 토큰을 줍니다 (예: 123456789:ABCdef...)")
print()

bot_token = input("봇 토큰을 입력하세요: ").strip()

# 봇 정보 확인
resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
if not resp.ok:
    print(f"❌ 잘못된 토큰입니다: {resp.text}")
    exit(1)

bot_name = resp.json()["result"]["username"]
print(f"\n✓ 봇 확인: @{bot_name}")
print()
print("📱 다음 단계:")
print(f"  텔레그램에서 @{bot_name} 을 검색해서 대화를 시작하고")
print("  아무 메시지나 하나 보내세요. (예: 안녕)")
print()
input("메시지를 보낸 후 Enter를 누르세요...")

# 채팅 ID 조회
resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=10)
updates = resp.json().get("result", [])

if not updates:
    print("❌ 메시지를 받지 못했습니다. 봇에게 메시지를 보낸 후 다시 실행하세요.")
    exit(1)

chat_id = updates[-1]["message"]["chat"]["id"]
print(f"✓ 채팅 ID: {chat_id}")

# 테스트 메시지 전송
resp = requests.post(
    f"https://api.telegram.org/bot{bot_token}/sendMessage",
    json={"chat_id": chat_id, "text": "✅ 증시 알리미 연결 성공!\n매일 오전 8시에 증시 현황을 보내드릴게요."},
    timeout=10,
)

if resp.ok:
    print("\n✅ 테스트 메시지 전송 성공! 텔레그램을 확인하세요.")
else:
    print(f"❌ 전송 실패: {resp.text}")
    exit(1)

print()
print("=" * 50)
print("🔐 GitHub Secrets에 아래 3가지를 등록하세요:")
print("   (저장소 → Settings → Secrets and variables → Actions → New repository secret)")
print()
print(f"  TELEGRAM_BOT_TOKEN = {bot_token}")
print(f"  TELEGRAM_CHAT_ID   = {chat_id}")
print()
print("  ANTHROPIC_API_KEY  = https://console.anthropic.com 에서 발급")
print("=" * 50)
