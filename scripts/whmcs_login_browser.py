#!/usr/bin/env python3
"""
Đăng nhập WHMCS qua trình duyệt - mở browser, user đăng nhập thủ công (giải CAPTCHA),
sau đó script tự lấy cookies và gửi lên API hoặc in ra để paste.

Flow:
1. Mở trình duyệt (visible)
2. Điều hướng đến trang login WHMCS
3. User đăng nhập (giải CAPTCHA nếu có)
4. Chờ redirect sang trang ticket list
5. Lấy cookies → gửi lên API hoặc in JSON

Usage:
  # In cookies ra stdout (paste vào app)
  python scripts/whmcs_login_browser.py

  # Gửi trực tiếp lên API
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
    print("Cần cài playwright: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

try:
    import httpx
except ImportError:
    httpx = None


def main():
    parser = argparse.ArgumentParser(
        description="Đăng nhập WHMCS qua trình duyệt - user login thủ công, script lấy cookies"
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
        help="Path chứa trong URL khi đăng nhập thành công (để detect)",
    )
    parser.add_argument(
        "--api-url",
        default="",
        help="API base URL (e.g. http://localhost:8000/v1) - nếu có sẽ POST cookies lên /admin/save-whmcs-cookies",
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
        help="Thời gian chờ đăng nhập (giây), mặc định 5 phút",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    login_url = f"{base}/{args.login_path.lstrip('/')}"
    success_path = args.success_path

    # Trong Docker không có display - script cần chạy trên máy local
    in_docker = Path("/.dockerenv").exists()
    if in_docker:
        print("Script này cần chạy trên máy local (có màn hình), không chạy trong Docker.")
        print("Chạy từ thư mục project trên máy của bạn:")
        print(f"  python scripts/whmcs_login_browser.py --api-url http://localhost:8000/v1 --api-key dev-key")
        print("(Đảm bảo API đang chạy và port 8000 được map từ Docker nếu dùng Docker.)")
        sys.exit(1)

    print(f"Mở trình duyệt: {login_url}")
    print("→ Đăng nhập thủ công (giải CAPTCHA nếu có). Script sẽ tự lấy cookies khi chuyển sang trang ticket.")
    print("  (Chạy từ thư mục gốc project: cd auto-reply-chatbot)")
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

        # Chờ user đăng nhập - URL chuyển sang chứa success_path (vd supporttickets)
        try:
            page.wait_for_url(
                lambda u: success_path in u,
                timeout=args.timeout * 1000,
            )
        except Exception as e:
            print(f"Timeout hoặc lỗi: {e}")
            print("Đảm bảo đã đăng nhập thành công và chuyển sang trang ticket.")
            browser.close()
            sys.exit(1)

        # Lấy cookies
        raw_cookies = context.cookies()
        # Chuyển sang format giống EditThisCookie
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
        print("Không lấy được cookie.")
        sys.exit(1)

    print(f"Đã lấy {len(cookies)} cookies.")

    if args.api_url:
        if not httpx:
            print("Cần cài httpx: pip install httpx")
            print("Hoặc chạy không có --api-url để in cookies ra, rồi paste vào app.")
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
            print(f"Đã gửi cookies lên API: {data.get('count', 0)} cookies đã lưu.")
        except Exception as e:
            print(f"Gửi API thất bại: {e}")
            print("Cookies (paste thủ công):")
            print(json.dumps(cookies, indent=2, ensure_ascii=False))
    else:
        print("Cookies (copy và dán vào ô Session Cookies trong app):")
        print(json.dumps(cookies, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
