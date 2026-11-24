#!/usr/bin/env python3
"""Receives notes and short-lived audio links from a logged-in voicenotes.com tab (browser_bridge.js)
and feeds them to full_export.py, so no token leaves the browser.

  browser_bridge.py --dir WORK --ids ids.json --downloader 'CMD'   # CMD reads the links JSON on stdin

Listens on 127.0.0.1 only, under a random path written to WORK/url. Accepts the voicenotes.com origin only.
Links are kept in memory, never written to disk. Progress: WORK/status.json. Listing pages: WORK/pages/N.json.
"""
import argparse
import json
import os
import secrets
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--dir", type=Path, required=True)
ap.add_argument("--ids", type=Path, required=True)
ap.add_argument("--downloader", required=True)
ap.add_argument("--port", type=int, default=8977)
ap.add_argument("--batch-seconds", type=int, default=45, help="links expire in about 10 minutes")
a = ap.parse_args()
os.umask(0o077)
(a.dir / "pages").mkdir(parents=True, exist_ok=True)
base = "/" + secrets.token_urlsafe(16)
ORIGIN = "https://voicenotes.com"
lock, queue = threading.Lock(), []
st = {"links": 0, "pages": 0, "by_status": {}, "last_seen": None, "client": None, "downloader": None, "dl_failures": 0, "browser_done": False, "finished": False}


def save():
    tmp = a.dir / "status.tmp"
    tmp.write_text(json.dumps(st))
    tmp.replace(a.dir / "status.json")


class H(BaseHTTPRequestHandler):
    def log_message(self, *x): ...

    def reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def ok(self):
        return self.path.startswith(base + "/") and self.headers.get("Origin") in (ORIGIN, None)

    def do_OPTIONS(self):
        self.reply(204 if self.ok() else 403)

    def do_GET(self):
        if not self.ok():
            return self.reply(403)
        have = sorted(int(p.stem) for p in (a.dir / "pages").glob("*.json"))
        self.reply(200, json.dumps({"ids": json.loads(a.ids.read_text()), "pages": have}).encode())

    def do_POST(self):
        if not self.ok():
            return self.reply(403)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with lock:
            if self.path.endswith("/page"):
                n = int(body["page"])
                tmp = a.dir / "pages" / f"{n}.tmp"
                tmp.write_text(json.dumps(body, ensure_ascii=False))
                tmp.replace(a.dir / "pages" / f"{n}.json")
                st["pages"] = len(list((a.dir / "pages").glob("*.json")))
            elif self.path.endswith("/links"):
                queue.extend(body)
                st["links"] += len(body)
                for x in body:
                    k = str(x["status"])
                    st["by_status"][k] = st["by_status"].get(k, 0) + 1
            elif self.path.endswith("/beat"):
                st["client"] = body
                st["browser_done"] = bool(body.get("done"))
            st["last_seen"] = time.strftime("%H:%M:%S")
            save()
        self.reply(200)


def pump():
    while True:
        for _ in range(a.batch_seconds):
            time.sleep(1)
            if st["browser_done"]:
                break
        with lock:
            batch, queue[:] = queue[:], []
        if batch:
            p = subprocess.run(shlex.split(a.downloader), input=json.dumps(batch), capture_output=True, text=True)
            st["downloader"] = (p.stdout.strip().splitlines() or p.stderr.strip()[-300:].splitlines() or [""])[-1]
            st["dl_failures"] += p.returncode != 0
        elif st["browser_done"]:
            st["finished"] = True
            save()
            os._exit(0)
        save()


srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
(a.dir / "url").write_text(f"http://127.0.0.1:{a.port}{base}")
save()
threading.Thread(target=pump, daemon=True).start()
srv.serve_forever()
