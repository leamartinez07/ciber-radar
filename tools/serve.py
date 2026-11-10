#!/usr/bin/env python3
"""Sirve public/ como Vercel: URLs limpias, 404 propio, cabeceras de vercel.json y gzip."""
import gzip
import http.server
import json
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
CONFIG = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
RULES = [(re.compile("^" + rule["source"] + "$"), rule["headers"]) for rule in CONFIG["headers"]]
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/manifest+json", ".webmanifest")
COMPRESSIBLE = ("text/", "application/javascript", "application/json", "application/manifest", "application/xml", "image/svg")


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def resolve(self, path: str):
        target = (PUBLIC / path.lstrip("/")).resolve()
        if not target.is_relative_to(PUBLIC):
            return None
        if path == "/":
            return PUBLIC / "index.html"
        if target.is_file():
            return target
        page = target.with_name(target.name + ".html")
        return page if page.is_file() else None

    def do_HEAD(self):
        self.do_GET(send_body=False)

    def do_GET(self, send_body=True):
        path = self.path.split("?", 1)[0]
        target = self.resolve(path)
        status = 200 if target else 404
        target = target or PUBLIC / "404.html"
        body = target.read_bytes()
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") else ""))
        cache = "public, max-age=0, must-revalidate"
        for pattern, headers in RULES:
            if pattern.match(path):
                for header in headers:
                    if header["key"] == "Cache-Control":
                        cache = header["value"]
                    elif header["key"] != "Strict-Transport-Security":
                        self.send_header(header["key"], header["value"])
        self.send_header("Cache-Control", cache)
        if kind.startswith(COMPRESSIBLE) and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = gzip.compress(body, 9)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
