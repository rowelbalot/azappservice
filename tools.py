import requests
from html.parser import HTMLParser
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current information on any topic. "
                "Use this when you need up-to-date or real-time information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "Fetch and read the text content of a specific webpage URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the webpage to fetch",
                    }
                },
                "required": ["url"],
            },
        },
    },
]


class _HtmlStripper(HTMLParser):
    _SKIP = frozenset({"script", "style", "nav", "footer", "header", "aside"})

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self):
        return " ".join(self._parts)


def web_search(query: str) -> str:
    try:
        results = list(DDGS().text(query, max_results=5))
        if not results:
            return "No results found."
        parts = [
            f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}"
            for r in results
        ]
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Search error: {exc}"


def fetch_webpage(url: str) -> str:
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ChatApp/1.0)"},
        )
        resp.raise_for_status()
        parser = _HtmlStripper()
        parser.feed(resp.text)
        text = " ".join(parser.get_text().split())
        return text[:5000] + ("..." if len(text) > 5000 else "")
    except Exception as exc:
        return f"Fetch error: {exc}"


def execute_tool(name: str, args: dict) -> str:
    if name == "web_search":
        return web_search(args.get("query", ""))
    if name == "fetch_webpage":
        return fetch_webpage(args.get("url", ""))
    return f"Unknown tool: {name}"
