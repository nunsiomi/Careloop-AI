"""Tiny web server that tells Twilio to pass calls to Tomi through LiveKit (works on a Twilio trial).

Twilio's trial blocks SIP trunking and TwiML Bins, but it still fetches call instructions (TwiML) from a web
address you run. This server answers those requests only on a secret address (a new random secret every run),
because the TwiML holds the LiveKit SIP password. It starts a free Cloudflare tunnel so Twilio can reach your
laptop, and saves the secret address in voice/.tunnel-url for dial.py.

Run:  python twiml_server.py          (needs cloudflared: winget install Cloudflare.cloudflared)
Then: python tomi_agent.py dev, and python dial.py +234... in other terminals.
Routes: POST /<secret>/twiml/outbound (dial.py calls), POST /<secret>/twiml/inbound (your Twilio number's
voice webhook; printed at start).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape

import httpx
from dotenv import load_dotenv

from setup_sip import twiml

PORT = int(os.getenv("TWIML_PORT", "8787"))
URL_FILE = Path(__file__).parent / ".tunnel-url"
public_url = os.getenv("TWILIO_WEBHOOK_BASE", "").rstrip("/")
# A new random secret every run, in every address Twilio is given. Only dial.py and Twilio learn it, so nobody
# who finds the tunnel can read the LiveKit SIP password. (Twilio's signature header proved fragile here.)
SECRET = os.getenv("TWIML_SECRET") or secrets.token_urlsafe(18)


def signature_ok(url: str, params: dict[str, str], signature: str) -> bool:
    """Twilio's request signature: HMAC-SHA1 of the URL plus every POST field, sorted by name. Logged only."""
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(os.environ["TWILIO_AUTH_TOKEN"].encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._send(200, "text/plain", "CareLoop TwiML server is running.")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        params = dict(parse_qsl(self.rfile.read(length).decode(), keep_blank_values=True))
        prefix = f"/{SECRET}/"
        if not self.path.startswith(prefix):
            self._send(403, "text/plain", "Forbidden")
            return
        route = "/" + self.path[len(prefix):].split("?")[0]
        if not signature_ok(public_url + self.path, params, self.headers.get("X-Twilio-Signature", "")):
            print("  (Twilio's signature did not match TWILIO_AUTH_TOKEN; is it the primary Auth Token?)", flush=True)
        if route == "/twiml/outbound":
            body = twiml(params.get("To"))  # Twilio rang the patient: To is their number
        elif route == "/twiml/inbound":
            body = twiml(params.get("From"))  # the patient rang us: From is their number
        elif route == "/twiml/stream-test":
            # Probe: does a trial account allow <Connect><Stream>? There is no audio server behind it yet, so
            # the call ends after the line below; Twilio's error code then says whether streams are allowed.
            ws = public_url.replace("https://", "wss://") + f"/{SECRET}/stream"
            body = (f'<Response><Say>Stream test.</Say><Connect><Stream url="{escape(ws)}"/></Connect>'
                    "<Say>The stream ended.</Say></Response>")
        else:
            self._send(404, "text/plain", "Not found")
            return
        self._send(200, "application/xml", body)

    def _send(self, status: int, kind: str, body: str) -> None:
        # Log the route and status only; never the request body (it holds phone numbers).
        if self.command == "POST":
            note = {403: " (wrong address: restart dial.py after restarting this server)", 404: " (unknown route)"}.get(status, "")
            route = self.path.replace(SECRET, "<secret>").split("?")[0]
            print(f"{time.strftime('%H:%M:%S')} Twilio asked {route} -> {status}{note}", flush=True)
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        pass  # _send logs each Twilio request


def start_tunnel() -> None:
    """Start a Cloudflare quick tunnel to this server and remember its public address."""
    global public_url
    # Terminals opened before the install (VS Code keeps the old PATH until it restarts) won't find it on PATH.
    install_dirs = [r"C:\Program Files (x86)\cloudflared", r"C:\Program Files\cloudflared"]
    exe = shutil.which("cloudflared") or next(
        (str(Path(d) / "cloudflared.exe") for d in install_dirs if (Path(d) / "cloudflared.exe").exists()), None
    )
    if not exe:
        sys.exit("cloudflared is not installed. Run: winget install Cloudflare.cloudflared, then open a new terminal.")
    proc = subprocess.Popen(
        [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
        stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
    )
    for row in proc.stderr:
        found = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", row)
        if found:
            public_url = found.group(0)
            break
    # Keep reading so cloudflared never blocks on a full pipe.
    threading.Thread(target=lambda: [None for _ in proc.stderr], daemon=True).start()
    if not public_url:
        sys.exit("The Cloudflare tunnel did not start. Check your internet connection and try again.")


def announce() -> None:
    """Save the secret address for dial.py and print the one for incoming calls."""
    URL_FILE.write_text(f"{public_url}/{SECRET}", encoding="utf-8")
    print(f"Ready. Public address: {public_url}")
    print("For people ringing your Twilio number, set its Voice webhook (HTTP POST) to:")
    print(f"  {public_url}/{SECRET}/twiml/inbound")


def wait_until_public() -> None:
    """A new tunnel takes a few seconds to work on the internet. Only hand out the address once it does."""
    print(f"Tunnel address: {public_url} (checking it works from the internet...)")
    for _ in range(30):
        try:
            if httpx.get(public_url + "/", timeout=5).status_code == 200:
                announce()
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    print("The tunnel address still does not answer after a minute. Stop this (Ctrl+C) and start it again.")


if __name__ == "__main__":
    load_dotenv()
    missing = [k for k in ("TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "LIVEKIT_SIP_URI", "LIVEKIT_SIP_USERNAME", "LIVEKIT_SIP_PASSWORD") if not os.getenv(k)]
    if missing:
        sys.exit(f"Fill these in .env first: {', '.join(missing)}")
    public_url = os.getenv("TWILIO_WEBHOOK_BASE", "").rstrip("/")
    URL_FILE.unlink(missing_ok=True)  # an address from an earlier run is dead
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not public_url:
        print("Starting the Cloudflare tunnel...")
        start_tunnel()
        wait_until_public()
    else:
        announce()
    print(f"Listening on 127.0.0.1:{PORT}. Leave this running; Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        URL_FILE.unlink(missing_ok=True)
