"""T4's sources: three pages served from a local thread, and a fetch tool that only reaches them. No live web, no
firewall, no cost, deterministic — and the famous-date question has no page on purpose."""
from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from hypswarm.messages import Tool


class PageServer:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        srv = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = srv.pages.get(self.path.rstrip("/") or "/")
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>404</h1><p>No such page.</p></body></html>")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *a: Any) -> None:
                pass
        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.http.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.fetched: list[str] = []

    def index(self) -> str:
        return "Pages on this host: " + ", ".join(f"{self.base}{p}" for p in self.pages)

    def tool(self) -> Tool:
        srv = self

        def fetch(url: str) -> str:
            """GET a page on the local source host and return its visible text. Only this host exists; the index lists its pages."""
            import httpx
            if not url.startswith(srv.base):
                return f"refused: only {srv.base} is reachable. {srv.index()}"
            srv.fetched.append(url)
            r = httpx.get(url, timeout=5)
            if r.status_code != 200:
                return f"HTTP {r.status_code}: no such page. {srv.index()}"
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)).strip()
        return Tool.from_function(fetch)

    def close(self) -> None:
        self.http.shutdown()
