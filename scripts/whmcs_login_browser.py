#!/usr/bin/env python3
"""
WHMCS login via browser - open browser, user logs in manually (solve CAPTCHA if any),
then script fetches cookies and sends to API or prints for paste.

Flow:
1. Open browser (visible)
2. Navigate to WHMCS login page
3. User logs in (solve CAPTCHA if any)
4. Wait for redirect to ticket list page
5. Get cookies → send to API or print JSON

Usage:
  # Print cookies to stdout (paste into app)
  python scripts/whmcs_login_browser.py

  # Send directly to API
  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key

  # Custom base URL
  python scripts/whmcs_login_browser.py --base-url https://greencloudvps.com/billing/greenvps
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Install playwright: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

try:
    import httpx
except ImportError:
    httpx = None


def main():
    parser = argparse.ArgumentParser(
        description="WHMCS login via browser - user logs in manually, script fetches cookies"
    )
    parser.add_argument(
        "--base-url",
        default="https://greencloudvps.com/billing/greenvps",
        help="WHMCS base URL",
    )
    parser.add_argument(
        "--login-path",
        default="login.php",
        help="Login page path",
    )
    parser.add_argument(
        "--success-path",
        default="supporttickets.php",
        help="Path contained in URL when login succeeds (for detection)",
    )
    parser.add_argument(
        "--api-url",
        default="",
        help="API base URL (e.g. http://localhost:8000/v1) - if set, POST cookies to /admin/save-whmcs-cookies",
    )
    parser.add_argument(
        "--api-key",
        default="dev-key",
        help="X-Admin-API-Key",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Login wait timeout (seconds), default 5 minutes",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    login_url = f"{base}/{args.login_path.lstrip('/')}"
    success_path = args.success_path

    # No display in Docker - script must run on local machine
    in_docker = Path("/.dockerenv").exists()
    if in_docker:
        print("This script must run on local machine (with display), not in Docker.")
        print("Run from project folder on your machine:")
        print(f"  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key")
        print("(Ensure API is running and port 8000 is mapped from Docker if using Docker.)")
        sys.exit(1)

    print(f"Opening browser: {login_url}")
    print("→ Log in manually (solve CAPTCHA if any). Script will fetch cookies when you reach ticket page.")
    print("  (Run from project root: cd auto-reply-chatbot)")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for user to log in - URL changes to contain success_path (e.g. supporttickets)
        try:
            page.wait_for_url(
                lambda u: success_path in u,
                timeout=args.timeout * 1000,
            )
        except Exception as e:
            print(f"Timeout or error: {e}")
            print("Ensure you logged in successfully and reached the ticket page.")
            browser.close()
            sys.exit(1)

        # Get cookies
        raw_cookies = context.cookies()
        # Convert to EditThisCookie-like format
        cookies = []
        for c in raw_cookies:
            cookies.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
                "sameSite": c.get("sameSite"),
            })

        browser.close()

    if not cookies:
        print("Failed to get cookies.")
        sys.exit(1)

    print(f"Got {len(cookies)} cookies.")

    if args.api_url:
        if not httpx:
            print("Install httpx: pip install httpx")
            print("Or run without --api-url to print cookies, then paste into app.")
            sys.exit(1)
        api_base = args.api_url.rstrip("/")
        url = f"{api_base}/admin/save-whmcs-cookies"
        try:
            r = httpx.post(
                url,
                json={"session_cookies": cookies},
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-API-Key": args.api_key,
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            print(f"Sent cookies to API: {data.get('count', 0)} cookies saved.")
        except Exception as e:
            print(f"API send failed: {e}")
            print("Cookies (paste manually):")
            print(json.dumps(cookies, indent=2, ensure_ascii=False))
    else:
        print("Cookies (copy and paste into Session Cookies field in app):")
        print(json.dumps(cookies, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
