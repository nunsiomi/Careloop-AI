"""One-time helper: sign in with Google and save GMAIL_REFRESH_TOKEN to ../.env (it is never printed).

Needs GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in ../.env first (a "Desktop app" OAuth client with the Gmail API
enabled). Run from backend/: python gmail_token.py. A browser opens; sign in as the EMAIL_FROM address and allow it.
"""

import http.server
import secrets
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ENV = Path(__file__).resolve().parent.parent / ".env"
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/"


def main() -> None:
    config = dotenv_values(ENV)
    client_id, client_secret = config.get("GMAIL_CLIENT_ID"), config.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(f"Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in {ENV} first.")
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "state": state,
        "scope": "https://www.googleapis.com/auth/gmail.send", "access_type": "offline", "prompt": "consent"})
    answer = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            answer.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

        def log_message(self, *args):
            pass

    print("Opening Google sign-in. If no browser opens, visit:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as server:
        while "code" not in answer and "error" not in answer:
            server.handle_request()
    if answer.get("state", [""])[0] != state or "code" not in answer:
        raise SystemExit(f"Google did not give a code: {answer.get('error', ['wrong state'])[0]}")
    response = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": answer["code"][0], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=15)
    token = response.json().get("refresh_token")
    if not token:
        raise SystemExit(f"No refresh token ({response.status_code}): {response.text[:300]}")
    set_key(str(ENV), "GMAIL_REFRESH_TOKEN", token, quote_mode="never")
    print(f"Saved GMAIL_REFRESH_TOKEN to {ENV}.")


if __name__ == "__main__":
    main()
