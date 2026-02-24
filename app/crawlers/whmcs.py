"""WHMCS ticket crawler - crawl ticket list and detail pages.

Flow:
1. Login (if credentials provided)
2. Mỗi list page: lấy IDs → crawl detail ngay (supporttickets.php?action=view&id=XXX) → sang list page tiếp
3. ticket_queue: put mỗi ticket ngay khi crawl xong (save DB async)
4. Bỏ qua ticket cảnh báo hệ thống (Monitor, Hypervisor, cpu usage, load average, Server Reboot) - lưu ID vào skipped list
5. Return list of ticket dicts
"""

import json
import os
import queue
from datetime import datetime
from pathlib import Path

# Must be set before importing playwright.
# Respect existing env first, then fallback to known Docker locations.
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    for candidate in ("/ms-playwright", "/app/ms-playwright"):
        if os.path.exists(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate
            break

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from playwright.sync_api import Page, sync_playwright

from app.core.logging import get_logger

logger = get_logger(__name__)

# Ticket subject patterns = system alerts/notifications → skip crawl, lưu ID vào skipped list
_SKIP_PATTERNS = (
    "monitor is down",
    "monitor is up",
    "hypervisor connection check failed",
    "hypervisor connection check recovered",
    "server reboot alert",
    "cpu usage (",
    "load average",
)


def _is_system_alert_ticket(subject: str | None) -> bool:
    """True nếu subject là ticket cảnh báo hệ thống (Monitor, Hypervisor, cpu/load)."""
    if not subject or not subject.strip():
        return False
    s = subject.lower().strip()
    for pat in _SKIP_PATTERNS:
        if pat in s:
            return True
    # CLOSED - / OPEN - kèm theo tên server (ví dụ: CLOSED - SG2- MILAN3 - 96.9.210.15 load average)
    if ("closed - " in s or "open - " in s) and ("cpu usage" in s or "load average" in s):
        return True
    return False


def _get_skipped_tickets_path() -> Path:
    """Đường dẫn file lưu danh sách ticket ID bị skip."""
    for base in (Path("/app"), Path.cwd()):
        candidate = base / "source" / "skipped_ticket_ids.json"
        if candidate.parent.exists():
            return candidate
    return Path.cwd() / "source" / "skipped_ticket_ids.json"


def _load_skipped_ids() -> set[str]:
    """Load set các ticket ID đã skip từ file."""
    path = _get_skipped_tickets_path()
    if not path.exists():
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ids = data.get("ids", [])
        return set(str(x) for x in ids)
    except Exception:
        return set()


def _save_skipped_id(tid: str, existing: set[str]) -> None:
    """Thêm ticket ID vào danh sách skip và ghi file."""
    existing.add(tid)
    path = _get_skipped_tickets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"ids": sorted(existing), "updated_at": datetime.utcnow().isoformat() + "Z"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@dataclass
class WHMCSConfig:
    """Config for WHMCS crawler."""

    base_url: str = "https://greencloudvps.com/billing/greenvps"
    list_path: str = "supporttickets.php?filter=1"
    login_path: str = "login.php"
    username: str | None = None
    password: str | None = None
    totp_code: str | None = None  # 2FA code (6 digits from authenticator app)
    session_cookies: list[dict[str, Any]] | None = None  # Bypass login: paste cookies from browser
    headless: bool = True
    timeout_ms: int = 30000


def _full_url(base: str, path: str) -> str:
    """Build full URL from base and path."""
    if path.startswith("http"):
        return path
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}" if not base.endswith("/") else f"{base}{path}"


def _extract_token_from_url(url: str) -> str | None:
    """Extract token param from URL for pagination."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    tokens = params.get("token", [])
    return tokens[0] if tokens else None


def _get_domain_from_url(url: str) -> str:
    """Extract domain for cookies (e.g. greencloudvps.com)."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _login_if_needed(page: Page, config: WHMCSConfig) -> bool:
    """Login to WHMCS: use session_cookies if provided, else username/password."""
    # Mode 1: Session cookies - navigate to domain first, then add cookies (bypass CAPTCHA)
    if config.session_cookies:
        try:
            cookies = _build_cookies_for_playwright(config.session_cookies, config.base_url)
            if cookies:
                # Navigate to base first so storage partition is set, then add cookies
                page.goto(config.base_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
                page.context.add_cookies(cookies)
                logger.info("whmcs_crawler_cookies_injected", count=len(cookies))
                return True
        except Exception as e:
            logger.warning("whmcs_crawler_cookies_failed", error=str(e))

    # Mode 2: Username/password (blocked by CAPTCHA on many WHMCS)
    if not config.username or not config.password:
        logger.info("whmcs_crawler_no_credentials", msg="Skipping login (no credentials)")
        return True

    login_url = _full_url(config.base_url, config.login_path)
    page.goto(login_url, wait_until="networkidle", timeout=config.timeout_ms)

    # Check if already logged in (no login form)
    user_input = page.query_selector('input[name="username"], input[name="email"], input[type="email"]')
    if not user_input:
        logger.info("whmcs_crawler_already_logged_in")
        return True

    # Step 1: username + password
    page.fill('input[name="username"], input[name="email"], input[type="email"]', config.username)
    page.fill('input[name="password"], input[type="password"]', config.password)
    page.click('button[type="submit"], input[type="submit"], button:has-text("Login")')
    page.wait_for_load_state("networkidle", timeout=config.timeout_ms)

    # Check for login error
    if "incorrect" in page.content().lower() or "invalid" in page.content().lower():
        logger.warning("whmcs_crawler_login_failed")
        return False

    # Step 2: 2FA if required
    totp_input = page.query_selector(
        'input[name="twofa"], input[name="code"], input[name="twofactorauth"], '
        'input[placeholder*="code" i], input[placeholder*="authenticator" i], '
        'input[id*="twofa"], input[id*="2fa"]'
    )
    if totp_input and config.totp_code:
        page.fill(
            'input[name="twofa"], input[name="code"], input[name="twofactorauth"], '
            'input[placeholder*="code" i], input[placeholder*="authenticator" i], '
            'input[id*="twofa"], input[id*="2fa"]',
            config.totp_code.strip(),
        )
        page.click('button[type="submit"], input[type="submit"], button:has-text("Verify"), button:has-text("Submit")')
        page.wait_for_load_state("networkidle", timeout=config.timeout_ms)
        if "incorrect" in page.content().lower() or "invalid" in page.content().lower():
            logger.warning("whmcs_crawler_2fa_failed")
            return False
        logger.info("whmcs_crawler_2fa_ok")
    elif totp_input and not config.totp_code:
        logger.warning("whmcs_crawler_2fa_required", msg="2FA input found but no totp_code provided")
        return False

    logger.info("whmcs_crawler_login_ok")
    return True


def _collect_ticket_ids_from_page(page: Page, base_url: str) -> list[str]:
    """
    Extract ticket IDs from current list page (chỉ lấy id, không lấy nội dung).
    WHMCS table: <a href="supporttickets.php?action=view&id=XXX">
    """
    ids: list[str] = []
    seen: set[str] = set()

    anchors = page.query_selector_all('a[href*="supporttickets.php"][href*="action=view"][href*="id="]')
    for a in anchors:
        href = a.get_attribute("href")
        if not href:
            continue
        tid = _extract_ticket_id_from_url(urljoin(base_url + "/", href))
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(tid)
    return ids


def _is_list_url(url: str) -> bool:
    """URL là trang list (filter=1&page=N), không phải trang detail (action=view&id=)."""
    return "action=view" not in url and ("filter=" in url or "page=" in url)


def _get_next_page_url(
    page: Page,
    current_url: str,
    base_url: str,
    list_path: str,
    *,
    current_page_num: int | None = None,
) -> str | None:
    """
    Find next pagination URL. Chỉ dùng list URL (filter=1&page=N).
    Bỏ qua link action=view (trang detail ticket) - Next button có thể trỏ sai.
    current_page_num: dùng khi current_url là detail page (không có page param).
    """
    if current_page_num is not None:
        page_num = current_page_num
    else:
        curr_parsed = urlparse(current_url)
        curr_params = parse_qs(curr_parsed.query)
        page_num = int(curr_params.get("page", ["1"])[0])
    next_num = page_num + 1

    # 1. Tìm link pagination: supporttickets + page=N, KHÔNG phải action=view
    pagination_links = page.query_selector_all('a[href*="supporttickets"][href*="page="]')
    for a in pagination_links:
        href = a.get_attribute("href")
        if not href:
            continue
        resolved = urljoin(base_url + "/", href)
        if not _is_list_url(resolved):
            continue
        p = parse_qs(urlparse(resolved).query)
        if p.get("page") and p.get("page")[0] == str(next_num):
            return resolved

    # 2. Next link - chỉ dùng nếu là list URL (không phải action=view)
    next_link = page.query_selector('a:has-text("Next"), a:has-text("»"), a[rel="next"]')
    if next_link:
        href = next_link.get_attribute("href")
        if href:
            resolved = urljoin(base_url + "/", href)
            if "supporttickets" in resolved and _is_list_url(resolved):
                return resolved

    # 3. Build thủ công: filter=1&page=N
    list_url = _full_url(base_url, list_path)
    parsed = urlparse(list_url)
    params = dict(parse_qs(parsed.query))
    params["page"] = [str(next_num)]
    next_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(params, doseq=True)}"
    return next_url


def _crawl_list_and_details(
    page: Page,
    config: WHMCSConfig,
    ticket_queue: queue.Queue | None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Crawl list page → lấy IDs → crawl detail từng ticket ngay → sang list page tiếp.
    Mỗi list page xong thì crawl content luôn, không đợi hết list.
    Bỏ qua ticket đã có trong skipped_ids; ticket mới match system alert → thêm vào skipped, không lưu DB.
    """
    tickets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    skipped_ids: set[str] = _load_skipped_ids()
    skipped_initial = len(skipped_ids)
    skipped_this_run = 0
    list_url = _full_url(config.base_url, config.list_path)
    base = config.base_url.rstrip("/")
    max_pages = 500

    page.goto(list_url, wait_until="networkidle", timeout=config.timeout_ms)
    current_url = page.url
    page_count = 0

    while page_count < max_pages:
        page_count += 1
        ids = _collect_ticket_ids_from_page(page, config.base_url)
        added = 0

        # Crawl detail ngay cho từng ID mới từ list page này
        for tid in ids:
            if tid in seen_ids:
                continue
            if tid in skipped_ids:
                seen_ids.add(tid)
                logger.debug("whmcs_crawler_skipped_known", id=tid)
                continue
            seen_ids.add(tid)
            added += 1
            detail_url = f"{base}/supporttickets.php?action=view&id={tid}"
            try:
                t = _extract_ticket_detail(page, detail_url)
                subject = t.get("subject") or ""
                if _is_system_alert_ticket(subject):
                    _save_skipped_id(tid, skipped_ids)
                    skipped_this_run += 1
                    logger.info(
                        "whmcs_crawler_skipped_system_alert",
                        id=tid,
                        subject=subject[:60],
                    )
                    continue
                tickets.append(t)
                if ticket_queue:
                    ticket_queue.put(t)
                logger.info(
                    "whmcs_crawler_detail",
                    id=tid,
                    list_page=page_count,
                    subject=subject[:60],
                    status=t.get("status"),
                )
            except Exception as e:
                logger.warning("whmcs_crawler_detail_failed", id=tid, error=str(e))

        sample_ids = ids[:8] if ids else []
        next_url = _get_next_page_url(
            page, current_url, config.base_url, config.list_path,
            current_page_num=page_count,
        )
        logger.info(
            "whmcs_crawler_list_page",
            page=page_count,
            url=current_url[:100],
            found=len(ids),
            new=added,
            total_seen=len(seen_ids),
            sample_ids=sample_ids,
            next_url=next_url[:100] if next_url else None,
        )

        if not next_url or next_url == current_url:
            break

        page.goto(next_url, wait_until="networkidle", timeout=config.timeout_ms)
        new_url = page.url

        if new_url == current_url:
            logger.info("whmcs_crawler_list_stop", reason="same_url_after_goto")
            break
        current_url = new_url

    logger.info(
        "whmcs_crawler_page_done",
        tickets_saved=len(tickets),
        skipped_this_run=skipped_this_run,
        skipped_total=len(skipped_ids),
    )
    return tickets, skipped_this_run


def _extract_ticket_id_from_url(url: str) -> str | None:
    """Extract ticket ID from URL like ...?action=view&id=12345"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    ids = params.get("id", [])
    return ids[0] if ids else None


def _extract_replies_from_page(page: Page) -> list[dict[str, Any]]:
    """
    Tách nội dung hội thoại từ div.reply.
    Mỗi reply: requestor-name, role (staff/owner), message content, postedon.
    """
    replies: list[dict[str, Any]] = []
    reply_els = page.query_selector_all("div.reply")

    for el in reply_els:
        name = ""
        name_el = el.query_selector(".requestor-name")
        if name_el:
            name = name_el.inner_text().strip()

        role = "owner"
        if el.query_selector(".requestor-type-operator, .requestor-type-staff, .reply.staff"):
            role = "staff"

        content = ""
        msg_el = el.query_selector(".message.markdown-content, .message")
        if msg_el:
            content = msg_el.inner_text().strip()

        posted = ""
        posted_el = el.query_selector(".postedon")
        if posted_el:
            posted = posted_el.inner_text().strip()

        if name or content:
            replies.append({
                "role": role,
                "name": name,
                "content": content,
                "posted": posted,
            })

    return replies


def _extract_ticket_detail(page: Page, detail_url: str) -> dict[str, Any]:
    """Lấy nội dung ticket từ trang chi tiết supporttickets.php?action=view&id=XXX."""
    page.goto(detail_url, wait_until="networkidle", timeout=30000)

    ticket_id = _extract_ticket_id_from_url(detail_url) or "unknown"

    # Subject: h2, h3, .ticket-subject, .panel-heading
    subject = "Untitled"
    subject_el = page.query_selector("h2, h3, .ticket-subject, .panel-heading")
    if subject_el:
        subj_text = subject_el.inner_text().strip()
        if subj_text and len(subj_text) > 2:
            subject = subj_text

    # Hội thoại: div.reply -> replies[]
    replies = _extract_replies_from_page(page)
    description_parts: list[str] = []
    for r in replies:
        who = f"[{r['role']}] {r['name']}" if r.get("name") else r["role"]
        desc = f"{who}: {r.get('content', '')}"
        description_parts.append(desc)
    description = "\n\n".join(description_parts)[:10000] if description_parts else ""

    # Status
    status = "Open"
    status_el = page.query_selector(".ticket-status, .badge, [class*='status']")
    if status_el:
        status = status_el.inner_text().strip()[:64]

    # Priority
    priority = None
    prio_el = page.query_selector("[class*='priority'], .priority")
    if prio_el:
        priority = prio_el.inner_text().strip()[:32]

    # Email từ reply đầu (owner)
    email = None
    email_el = page.query_selector(".submitter a[href^='mailto:']")
    if email_el:
        href = email_el.get_attribute("href")
        if href and href.startswith("mailto:"):
            email = href[7:].strip()

    return {
        "external_id": ticket_id,
        "subject": subject,
        "description": description or subject,
        "status": status,
        "priority": priority,
        "client_id": None,
        "email": email,
        "name": replies[0].get("name") if replies else None,
        "detail_url": detail_url,
        "metadata": {"replies": replies},
    }


# Realistic Chrome UA - some sites reject headless/old UA
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _build_cookies_for_playwright(
    session_cookies: list[dict[str, Any]],
    base_url: str,
) -> list[dict[str, Any]]:
    """
    Build cookie list for Playwright.
    Preserve exact domain and path from each cookie - hostOnly cookies need domain without dot.
    """
    base = base_url.rstrip("/")
    parsed = urlparse(base)
    default_domain = parsed.netloc or _get_domain_from_url(base)
    cookies = []
    for c in session_cookies:
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        raw_domain = c.get("domain") or default_domain
        host_only = c.get("hostOnly", False)
        # hostOnly: domain "greencloudvps.com" (no dot). Else: ".greencloudvps.com"
        if host_only:
            domain = raw_domain.lstrip(".")
        else:
            domain = raw_domain if raw_domain.startswith(".") else f".{raw_domain}"
        path = c.get("path") or "/"
        secure = c.get("secure", True) if isinstance(c.get("secure"), bool) else True
        same_site = c.get("sameSite") or "Lax"
        if same_site and isinstance(same_site, str) and same_site.lower() in ("lax", "strict", "none"):
            same_site = same_site.capitalize() if same_site.lower() != "none" else "None"
        else:
            same_site = "Lax"
        entry = {
            "name": str(name),
            "value": str(value),
            "domain": domain,
            "path": path,
            "secure": secure,
            "sameSite": same_site,
        }
        cookies.append(entry)
    return cookies


def check_whmcs_cookies(
    base_url: str,
    list_path: str,
    session_cookies: list[dict[str, Any]],
    headless: bool = True,
    timeout_ms: int = 15000,
    debug: bool = False,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Check if cookies authenticate successfully.
    Returns (ok, message, debug_info). ok=True if we reach the ticket list (not redirected to login).
    """
    list_url = _full_url(base_url.rstrip("/"), list_path)
    base = base_url.rstrip("/")
    debug_info: dict[str, Any] = {} if debug else {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=_CHROME_UA,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()
        try:
            cookies = _build_cookies_for_playwright(session_cookies, base)
            if not cookies:
                return False, "Không có cookie hợp lệ", debug_info if debug else None

            if debug:
                debug_info["cookies_added"] = [
                    {"name": c["name"], "domain": c["domain"], "path": c["path"]}
                    for c in cookies
                ]
                debug_info["cookies_count"] = len(cookies)
                debug_info["list_url"] = list_url

            # Navigate to base first so storage partition is set, then add cookies
            page.goto(base, wait_until="domcontentloaded", timeout=timeout_ms)
            if debug:
                debug_info["after_goto_base"] = page.url

            page.context.add_cookies(cookies)
            page.goto(list_url, wait_until="networkidle", timeout=timeout_ms)
            final_url = page.url

            if debug:
                debug_info["final_url"] = final_url
                debug_info["page_title"] = page.title()
                debug_info["redirected_to_login"] = "login" in final_url.lower() or "redirect=supporttickets" in final_url

            # Redirected to login = auth failed
            if "login" in final_url.lower() or "redirect=supporttickets" in final_url:
                return False, f"Chưa đăng nhập được (redirect về {final_url[:80]}...)", debug_info if debug else None

            # Check for login form on page
            login_form = page.query_selector('input[name="username"], input[name="email"], input[type="email"]')
            if login_form:
                if debug:
                    debug_info["has_login_form"] = True
                return False, "Trang hiển thị form đăng nhập – cookies hết hạn hoặc không hợp lệ", debug_info if debug else None

            if debug:
                debug_info["has_login_form"] = False
            return True, "Kết nối thành công", debug_info if debug else None
        except Exception as e:
            logger.warning("whmcs_check_cookies_failed", error=str(e))
            if debug:
                debug_info["error"] = str(e)
            return False, str(e), debug_info if debug else None
        finally:
            browser.close()


def crawl_whmcs_tickets(
    config: WHMCSConfig,
    ticket_queue: queue.Queue | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Crawl WHMCS tickets: mỗi list page → lấy IDs → crawl detail ngay → sang list page tiếp.
    ticket_queue: put mỗi ticket ngay khi crawl xong (để save DB ngay).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.headless)
        context = browser.new_context(
            user_agent=_CHROME_UA,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()
        skipped = 0

        try:
            if not _login_if_needed(page, config):
                logger.error("whmcs_crawler_login_failed_abort")
                return [], 0

            tickets, skipped = _crawl_list_and_details(page, config, ticket_queue)
            logger.info("whmcs_crawler_done", count=len(tickets), skipped=skipped)
        finally:
            browser.close()

    if ticket_queue:
        ticket_queue.put(None)
    return tickets, skipped
