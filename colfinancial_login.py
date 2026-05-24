"""
COL Financial login simulation using the requests library.

Flow
----
1. HEAD www.colfinancial.com  →  follow redirects to find the assigned phXX node
2. GET  the API2_GetURL endpoint  →  parse JSON or redirect to resolve the real
   login-page URL on that node
3. GET  the login page  →  collect session cookies + every hidden form field
4. POST credentials (all fields)  →  follow all redirects automatically
5. Verify we land on the main/home page (URL + content check)
6. Confirm access to quotes/timesalesout.asp

Usage
-----
    python colfinancial_login.py --username <account_no> --password <password>

Environment variables (keep creds out of shell history):
    COL_USERNAME=<account_no> COL_PASSWORD=<password> python colfinancial_login.py
"""

import argparse
import json
import os
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Entry points ──────────────────────────────────────────────────────────────
BASE_URL          = "https://www.colfinancial.com"
GETURL_ENDPOINT   = f"{BASE_URL}/ape/API2_GetURL/p/geturl/s/SIGN_IN"

# Possible field names used by the old ASP platform (tried in order)
USERNAME_FIELDS   = ["txtAcctNum", "acctno", "acct_no", "account_no", "username", "userid"]
PASSWORD_FIELDS   = ["txtPassword", "pwd", "password", "pass", "passwd"]

# Indicators that we're on the authenticated main page (URL or content)
MAIN_URL_MARKERS  = [
    "/ape/Final2/home/",
    "/ape/final2/home/",
    "/ape/Final2_starter/home/",
    "/ape/API2/p/home",
    "/ape/API2/p/portfolio",
    "/ape/API2/p/dashboard",
]
MAIN_BODY_MARKERS = [
    "account summary",
    "market watch",
    "portfolio",
    "logout",
    "sign out",
    "log out",
    "trading",
]

QUOTES_PAGE      = "quotes/timesalesout.asp"

BROWSER_HEADERS  = {
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
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ── Step 1 – resolve the assigned phXX node via HEAD ─────────────────────────

def resolve_node(session: requests.Session) -> str:
    """
    HEAD www.colfinancial.com and follow all redirects.
    Returns the base URL of the final destination, e.g.
    'https://ph50.colfinancial.com'
    """
    print(f"[1] HEAD {BASE_URL}  →  tracing redirect chain …")
    resp = session.head(
        BASE_URL,
        headers=BROWSER_HEADERS,
        allow_redirects=True,
        timeout=30,
    )
    final = resp.url
    print(f"    Redirect chain:")
    for h in resp.history:
        print(f"      {h.status_code} → {h.url}")
    print(f"      {resp.status_code}   {final}  (final)")

    parsed = urlparse(final)
    node   = f"{parsed.scheme}://{parsed.netloc}"
    print(f"    Resolved node : {node}\n")
    return node


# ── Step 2 – get the real login URL from the API2_GetURL endpoint ─────────────

def resolve_login_url(session: requests.Session, node: str) -> str:
    """
    Call the API2_GetURL endpoint.  It may:
      a) Return a JSON body  {"url": "https://phXX.colfinancial.com/ape/…"}
      b) Issue an HTTP redirect straight to the login page
      c) Return HTML that contains a <meta http-equiv=refresh> or a login form
    Returns the resolved login-page URL.
    """
    print(f"[2] Resolving login URL via: {GETURL_ENDPOINT}")
    resp = session.get(
        GETURL_ENDPOINT,
        headers=BROWSER_HEADERS,
        allow_redirects=True,
        timeout=30,
    )
    print(f"    Status : {resp.status_code}   Final URL : {resp.url}")

    # (a) JSON response
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type or resp.text.strip().startswith("{"):
        try:
            data = json.loads(resp.text)
            url  = data.get("url") or data.get("URL") or data.get("redirect")
            if url:
                print(f"    JSON url : {url}\n")
                return url
        except json.JSONDecodeError:
            pass

    # (b) HTTP redirect already followed — final URL IS the login page
    if resp.history:
        print(f"    Followed HTTP redirect to: {resp.url}\n")
        return resp.url

    # (c) meta-refresh tag
    soup = BeautifulSoup(resp.text, "html.parser")
    meta = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
    if meta:
        content = meta.get("content", "")
        if "url=" in content.lower():
            url = content.split("=", 1)[1].strip().strip("'\"")
            url = urljoin(resp.url, url)
            print(f"    meta-refresh url : {url}\n")
            return url

    # (d) Fall back: build a best-guess login URL from the resolved node
    fallback = f"{node}/ape/Final2/login/login.asp"
    print(f"    Could not extract URL from response — using fallback: {fallback}\n")
    return fallback


# ── Step 3 – fetch login page, collect cookies + form fields ──────────────────

def fetch_login_page(session: requests.Session, login_url: str) -> tuple[str, dict]:
    """
    GET the login page.  Returns (form_action_url, pre_filled_fields).
    """
    print(f"[3] Fetching login page: {login_url}")
    resp = session.get(login_url, headers=BROWSER_HEADERS, timeout=30, allow_redirects=True)
    print(f"    Status : {resp.status_code}   Final URL : {resp.url}")
    print(f"    Cookies collected: {list(session.cookies.keys())}")

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        print("    [!] No <form> found — page may be JS-rendered.")
        print(f"    First 500 chars of body: {resp.text[:500]}")
        return resp.url, {}

    raw_action = form.get("action", "")
    action = urljoin(resp.url, raw_action) if raw_action else resp.url
    method = form.get("method", "POST").upper()

    fields: dict = {}
    for inp in form.find_all("input"):
        name  = inp.get("name")
        value = inp.get("value", "")
        if name:
            fields[name] = value

    print(f"    Form method : {method}")
    print(f"    Form action : {action}")
    print(f"    Discovered fields : {list(fields.keys())}\n")
    return action, fields


# ── Step 4 – POST credentials ─────────────────────────────────────────────────

def inject_credentials(fields: dict, username: str, password: str) -> dict:
    """
    Inject credentials into the form payload.
    Tries every known field-name variant; also replaces any existing
    placeholder values already in the form.
    """
    payload = dict(fields)

    # Find and set the username field
    user_key = next((k for k in payload if k.lower() in [f.lower() for f in USERNAME_FIELDS]), None)
    if user_key:
        payload[user_key] = username
        print(f"    Username → field '{user_key}'")
    else:
        # Fall back to the first name in our list
        payload[USERNAME_FIELDS[0]] = username
        print(f"    Username → field '{USERNAME_FIELDS[0]}' (assumed)")

    # Find and set the password field
    pass_key = next((k for k in payload if k.lower() in [f.lower() for f in PASSWORD_FIELDS]), None)
    if pass_key:
        payload[pass_key] = password
        print(f"    Password → field '{pass_key}'")
    else:
        payload[PASSWORD_FIELDS[0]] = password
        print(f"    Password → field '{PASSWORD_FIELDS[0]}' (assumed)")

    return payload


def post_login(
    session:   requests.Session,
    action:    str,
    payload:   dict,
    referer:   str,
) -> requests.Response:
    print(f"\n[4] POST {action}")
    resp = session.post(
        action,
        data=payload,
        headers={
            **BROWSER_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer":       referer,
            "Origin":        BASE_URL,
        },
        allow_redirects=True,
        timeout=30,
    )
    print(f"    Redirect chain:")
    for h in resp.history:
        print(f"      {h.status_code} → {h.url}")
    print(f"      {resp.status_code}   {resp.url}  (final)")
    print(f"    Session cookies: {list(session.cookies.keys())}\n")
    return resp


# ── Step 5 – verify main page ─────────────────────────────────────────────────

def is_main_page(resp: requests.Response) -> bool:
    url_lower  = resp.url.lower()
    body_lower = resp.text.lower()

    on_login   = any(x in url_lower for x in ("login", "sign_in", "logon"))
    url_match  = any(m.lower() in url_lower  for m in MAIN_URL_MARKERS)
    body_match = any(m.lower() in body_lower for m in MAIN_BODY_MARKERS)

    return (url_match or body_match) and not on_login


# ── Step 6 – confirm quotes/timesalesout.asp is reachable ────────────────────

def check_quotes_page(session: requests.Session, base_after_login: str) -> None:
    """
    Build the quotes URL relative to the authenticated node and GET it.
    Reports whether it's accessible or returns a login redirect.
    """
    parsed   = urlparse(base_after_login)
    # Strip down to  scheme://host/ape/FinalXX/
    path_parts = parsed.path.split("/")
    # Keep up to the 'ape' + 'FinalXX' segments
    try:
        ape_idx  = next(i for i, p in enumerate(path_parts) if p.lower() == "ape")
        base_path = "/".join(path_parts[:ape_idx + 2]) + "/"
    except StopIteration:
        base_path = "/"

    quotes_url = f"{parsed.scheme}://{parsed.netloc}{base_path}{QUOTES_PAGE}"
    print(f"[6] Checking quotes page: {quotes_url}")

    resp = session.get(
        quotes_url,
        headers={**BROWSER_HEADERS, "Referer": base_after_login},
        allow_redirects=True,
        timeout=30,
    )
    print(f"    Status : {resp.status_code}   Final URL : {resp.url}")

    if "login" in resp.url.lower() or "sign_in" in resp.url.lower():
        print("    [-] Redirected back to login — session may not have been established.")
    elif resp.status_code == 200:
        print("    [+] Quotes page is accessible.")
    else:
        print(f"    [?] Unexpected status {resp.status_code}.")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Simulate a COL Financial login using the requests library."
    )
    p.add_argument("--username", default=os.environ.get("COL_USERNAME", ""),
                   help="COL account number (or COL_USERNAME env var)")
    p.add_argument("--password", default=os.environ.get("COL_PASSWORD", ""),
                   help="COL password (or COL_PASSWORD env var)")
    p.add_argument("--debug", action="store_true",
                   help="Dump first 2000 chars of final response body on failure")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.username or not args.password:
        print(
            "Error: credentials required.\n"
            "  --username / COL_USERNAME  and  --password / COL_PASSWORD\n"
            "  must both be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    try:
        # 1. Find which phXX node handles this account
        node = resolve_node(session)

        # 2. Resolve the actual login-page URL
        login_url = resolve_login_url(session, node)

        # 3. Fetch login page → cookies + form fields
        action, fields = fetch_login_page(session, login_url)

        # 4. Inject credentials and POST
        print("[4] Injecting credentials …")
        payload  = inject_credentials(fields, args.username, args.password)
        response = post_login(session, action, payload, referer=login_url)

    except requests.RequestException as exc:
        print(f"\n[!] Network error: {exc}", file=sys.stderr)
        sys.exit(1)

    # 5. Verify main page
    print("[5] Verifying main page …")
    if is_main_page(response):
        print(f"    [+] LOGIN SUCCESSFUL — landed on: {response.url}")
    else:
        print(f"    [-] LOGIN FAILED or unexpected landing page: {response.url}")
        if args.debug:
            print("\n── Response body (first 2000 chars) ──")
            print(response.text[:2000])
        sys.exit(1)

    # 6. Confirm quotes page is accessible
    check_quotes_page(session, response.url)

    print("\n[+] All checks passed.")


if __name__ == "__main__":
    main()
