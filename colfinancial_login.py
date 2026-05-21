"""
COL Financial login simulation using the requests library.

Usage:
    python colfinancial_login.py --username <account_no> --password <password>

Or set environment variables:
    COL_USERNAME=<account_no> COL_PASSWORD=<password> python colfinancial_login.py
"""

import argparse
import os
import sys

import requests
from bs4 import BeautifulSoup

LOGIN_PAGE_URL = "https://www.colfinancial.com/ape/API2_GetURL/p/geturl/s/SIGN_IN"
MAIN_PAGE_INDICATORS = [
    "colfinancial.com/ape/API2/p/home",
    "colfinancial.com/ape/API2/p/portfolio",
    "colfinancial.com/ape/API2/p/main",
    "colfinancial.com/ape/API2/p/dashboard",
    "colfinancial.com/ape/API2/p/trade",
]
MAIN_PAGE_CONTENT_MARKERS = [
    "portfolio",
    "trade",
    "logout",
    "sign out",
    "account summary",
    "market watch",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def get_login_form(session: requests.Session) -> tuple[str, dict]:
    """Fetch the login page and extract the form action URL and all form fields."""
    print(f"[*] Fetching login page: {LOGIN_PAGE_URL}")
    response = session.get(LOGIN_PAGE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    # Follow any meta-refresh or JS redirects by checking the final URL
    print(f"[*] Login page resolved to: {response.url}")

    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form")
    if form is None:
        # Some SPAs render the form via JS; fall back to known field names
        print("[!] No <form> tag found — using known COL Financial field names.")
        return response.url, {}

    action = form.get("action", "")
    if action and not action.startswith("http"):
        from urllib.parse import urljoin
        action = urljoin(response.url, action)
    elif not action:
        action = response.url

    # Collect all pre-filled / hidden fields
    fields: dict = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            fields[name] = value

    print(f"[*] Form action  : {action}")
    print(f"[*] Pre-filled fields: {list(fields.keys())}")
    return action, fields


def login(username: str, password: str) -> requests.Response:
    """
    Perform a full login flow:
      1. Open a session (persists cookies).
      2. GET the login page → collect cookies + hidden form fields.
      3. POST credentials → follow all redirects automatically.
      4. Return the final response.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    action_url, form_fields = get_login_form(session)

    # Inject credentials using the known COL Financial field names.
    # The script also preserves any hidden/CSRF fields discovered above.
    form_fields["txtAcctNum"] = username   # account number field
    form_fields["txtPassword"] = password  # password field

    print(f"\n[*] Posting credentials to: {action_url}")
    response = session.post(
        action_url,
        data=form_fields,
        headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": LOGIN_PAGE_URL,
            "Origin": "https://www.colfinancial.com",
        },
        allow_redirects=True,   # follow all HTTP 301/302/303/307/308 redirects
        timeout=30,
    )

    print(f"[*] Final URL after redirects : {response.url}")
    print(f"[*] HTTP status               : {response.status_code}")
    print(f"[*] Redirect chain            :")
    for hist in response.history:
        print(f"      {hist.status_code} → {hist.url}")
    print(f"      {response.status_code}   {response.url}  (final)")

    return response


def confirm_main_page(response: requests.Response) -> bool:
    """
    Return True when the response looks like the authenticated main page.
    Checks both the final URL and page content keywords.
    """
    final_url = response.url.lower()

    # 1. URL-based check
    url_match = any(indicator in final_url for indicator in MAIN_PAGE_INDICATORS)

    # 2. Content-based check (case-insensitive keyword scan)
    body_lower = response.text.lower()
    content_match = any(marker in body_lower for marker in MAIN_PAGE_CONTENT_MARKERS)

    # 3. Make sure we're NOT still on the login page
    still_on_login = "sign_in" in final_url or "login" in final_url

    return (url_match or content_match) and not still_on_login


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate a COL Financial login using the requests library."
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("COL_USERNAME", ""),
        help="COL Financial account number (or set COL_USERNAME env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("COL_PASSWORD", ""),
        help="COL Financial password (or set COL_PASSWORD env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.username or not args.password:
        print(
            "Error: credentials required.\n"
            "  --username / COL_USERNAME  and  --password / COL_PASSWORD\n"
            "  must both be provided.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        response = login(args.username, args.password)
    except requests.RequestException as exc:
        print(f"[!] Network error: {exc}", file=sys.stderr)
        sys.exit(1)

    if confirm_main_page(response):
        print("\n[+] LOGIN SUCCESSFUL — landed on the main page.")
        sys.exit(0)
    else:
        print(
            "\n[-] LOGIN FAILED or redirected to an unexpected page.\n"
            f"    Final URL : {response.url}\n"
            "    Check your credentials or inspect the response HTML below:\n"
        )
        # Print the first 2000 characters of the response for debugging
        print(response.text[:2000])
        sys.exit(1)


if __name__ == "__main__":
    main()
