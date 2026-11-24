"""Fault-injection test against a fake API. Run: uv run --no-project --with requests --with pytest pytest -q tests"""
import json, os, random, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts/full_export.py"
N = 43
BODY = {f"r{i:03}": b"ID3" + random.Random(i).randbytes(3000 + i) for i in range(N)}


class S:
    flaky = True
    valid = "good"
    gone = {"r005"}
    hits: dict = {}
    downloads: list = []
    die_after = None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): ...

    def out(self, code, body=b"", length=None, **h):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body) if length is None else length))
        for k, v in h.items():
            self.send_header(k.replace("_", "-"), v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path
        n = S.hits[p] = S.hits.get(p, 0) + 1
        if p.startswith("/file/"):
            rid = p.split("/")[-1].split(".")[0]
            b = BODY[rid]
            if S.flaky and n == 1 and rid in ("r001", "r002"):
                self.out(200, b[:100], length=len(b))  # cut off
                self.close_connection = True
                return
            if S.flaky and n == 1 and rid == "r003":
                return self.out(200, b"<Error>expired</Error>")
            if S.flaky and n == 1 and rid == "r004":
                return self.out(403)
            S.downloads.append(rid)
            return self.out(200, b)
        if self.headers.get("Authorization") != f"Bearer {S.valid}" or (S.die_after and len(S.downloads) >= S.die_after):
            return self.out(401, b"{}")
        if p.startswith("/recordings?page="):
            pg = int(p.split("=")[1])
            if S.flaky and pg == 2 and n == 1:
                return self.out(500)
            if S.flaky and pg == 3 and n == 1:
                return self.out(429, Retry_After="0")
            ids = list(BODY)[(pg - 1) * 10 : pg * 10]
            return self.out(200, json.dumps({"data": [{"recording_id": i, "recorded_at": i, "transcript": "a b", "firebase_token": "SECRET"} for i in ids],
                                             "links": {"next": "x" if pg * 10 < N else None}}).encode())
        rid = p.split("/")[2]
        if rid in S.gone:
            return self.out(404, b"{}")
        self.out(200, json.dumps({"url": f"http://127.0.0.1:{self.server.server_port}/file/{rid}.mp3?sig=1"}).encode())


@pytest.fixture()
def run(tmp_path):
    S.flaky, S.valid, S.gone, S.hits, S.downloads, S.die_after = True, "good", {"r005"}, {}, [], None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    nobin = tmp_path / "bin"  # no ffprobe: the fixture audio is noise
    nobin.mkdir()

    def go(*args, token="good"):
        env = {"PATH": str(nobin), "VOICENOTES_API": f"http://127.0.0.1:{srv.server_port}", "VOICENOTES_BACKOFF": "0.01"}
        r = subprocess.run([sys.executable, str(SCRIPT), "--out", str(tmp_path / "o"), "--token-stdin", *args],
                           input=token + "\n", env=env, capture_output=True, text=True, timeout=60)
        rep = tmp_path / "o/report.json"
        return r, json.loads(rep.read_text()) if rep.exists() else None, tmp_path / "o"
    yield go
    srv.shutdown()


def test_survives_faults_and_is_byte_exact(run):
    r, rep, out = run()
    assert r.returncode == 0, r.stderr
    assert rep["notes"] == N and rep["audio"] == {"ok": N - 1, "no_audio": 1} and rep["complete"]
    for rid, b in BODY.items():
        if rid != "r005":
            assert (out / f"audio/{rid}.mp3").read_bytes() == b
    blob = b"".join(p.read_bytes() for p in out.rglob("*") if p.is_file() and p.suffix != ".mp3")
    assert b"SECRET" not in blob and b"good" not in blob and b"sig=1" not in blob
    n = len(S.downloads)
    assert run()[0].returncode == 0 and len(S.downloads) == n  # rerun fetches nothing


def test_token_dies_midway_then_resumes(run):
    S.die_after = 12
    r, rep, _ = run("--workers", "2")
    assert r.returncode == 3 and not rep["complete"]
    S.die_after = None
    r, rep, _ = run()
    assert r.returncode == 0 and rep["complete"] and len(S.downloads) == len(set(S.downloads))


def test_bad_token_creates_no_listing(run):
    r, rep, out = run(token="nope")
    assert r.returncode == 3 and not (out / "notes.jsonl").exists() and not rep["complete"]


def test_damaged_file_is_found_and_refetched(run):
    run()
    _, _, out = run()
    (out / "audio/r010.mp3").write_bytes(b"ID3 damaged")
    r, rep, _ = run("--verify")
    assert r.returncode == 1 and rep["problems"][0]["rid"] == "r010"
    r, rep, _ = run()
    assert r.returncode == 0 and (out / "audio/r010.mp3").read_bytes() == BODY["r010"]


def test_dump_adds_notes_and_keeps_old_ones(run, tmp_path):
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"records": [{"recording_id": "r005x", "transcript": "only in cache"}]}))
    S.gone = {"r005", "r005x"}
    r, rep, _ = run("--dump", str(d))
    assert r.returncode == 0 and rep["notes"] == N + 1
    assert run()[1]["notes"] == N + 1
