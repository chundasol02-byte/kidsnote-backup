#!/usr/bin/env python3
"""
Playwright login helper for Kidsnote.

로그인 후 sessionid를 환경변수(KIDSNOTE_SESSION_COOKIE)에 넣어
기존 fetch.py가 그대로 사용할 수 있도록 한다.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError


LOGIN_URL = "https://www.kidsnote.com/"

# GitHub Secrets에서 주입받을 계정 정보
EMAIL = os.environ.get("KIDSNOTE_EMAIL") or os.environ.get("KIDSNOTE_ID")
PASSWORD = os.environ.get("KIDSNOTE_PASSWORD")

if not EMAIL:
    print("[-] KIDSNOTE_EMAIL not found in environment variables.")
    sys.exit(1)

if not PASSWORD:
    print("[-] KIDSNOTE_PASSWORD not found in environment variables.")
    sys.exit(1)

# 디버깅용 스크린샷 저장 폴더
ARTIFACT_DIR = Path("playwright_artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)


async def save_debug(page, name):
    try:
        await page.screenshot(
            path=str(ARTIFACT_DIR / f"{name}.png"),
            full_page=True,
        )
        html = await page.content()
        (ARTIFACT_DIR / f"{name}.html").write_text(html, encoding="utf-8")
        print(f"[!] Saved debug screenshot and HTML to {ARTIFACT_DIR}/")
    except Exception as e:
        print(f"[-] Failed to save debug artifacts: {e}")


async def wait_until_logged_in(page):
    for _ in range(60):
        url = page.url
        if "/service" in url:
            return

        try:
            cookies = await page.context.cookies()
            for c in cookies:
                if c["name"] == "sessionid":
                    return
        except Exception:
            pass

        await page.wait_for_timeout(1000)

    raise RuntimeError("Login timeout - /service page or sessionid cookie not detected within 60s")


async def get_session_cookie(context):
    cookies = await context.cookies()
    for cookie in cookies:
        if cookie["name"] == "sessionid":
            return cookie["value"]
    return None


async def login():
    async with async_playwright() as p:
        print("[+] Launching headless Chromium...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("[+] Opening Kidsnote Main/Login Page...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        # 입력창이 나타날 때까지 명시적으로 잠시 대기
        await page.wait_for_selector('input[name="username"]', timeout=10000)
        
        # 아이디 입력
        print("[+] Filling username...")
        await page.locator('input[name="username"]').fill(EMAIL)

        # 비밀번호 입력
        print("[+] Filling password...")
        await page.locator('input[name="password"]').fill(PASSWORD)

        # 로그인 버튼 클릭
        print("[+] Clicking login button...")
        await page.locator('button[type="submit"]').click()

        print("[+] Waiting for redirection or session cookie...")
        try:
            # 로그인 처리 및 세션 쿠키 발급 대기
            await wait_until_logged_in(page)
            
            # 세션 쿠키 추출
            sessionid = await get_session_cookie(context)
            
            if not sessionid:
                print("[-] Failed to find 'sessionid' cookie after login.")
                await save_debug(page, "login_failed_no_cookie")
                sys.exit(1)
                
            print(f"[+] Successfully retrieved sessionid (len: {len(sessionid)})")
            
            # 1. GitHub Actions 시스템 환경 변수 ($GITHUB_ENV) 파일에 기록
            github_env_path = os.environ.get("GITHUB_ENV")
            if github_env_path:
                with open(github_env_path, "a", encoding="utf-8") as f:
                    f.write(f"KIDSNOTE_SESSION_COOKIE={sessionid}\n")
                print("[+] Saved KIDSNOTE_SESSION_COOKIE to GITHUB_ENV")
            
            # 2. 로컬 테스트 편의를 위해 .env 파일에도 보조 저장
            with open(".env", "a", encoding="utf-8") as f:
                f.write(f"\nKIDSNOTE_SESSION_COOKIE={sessionid}\n")
            print("[+] Saved KIDSNOTE_SESSION_COOKIE to .env")

        except Exception as e:
            print(f"[-] An error occurred during verification: {e}")
            await save_debug(page, "login_exception")
            sys.exit(1)
            
        finally:
            await browser.close()


def main():
    try:
        asyncio.run(login())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
