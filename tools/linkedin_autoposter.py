#!/usr/bin/env python3
"""Publish scheduled SkillMe posts through LinkedIn's official API.

Usage:
    python tools/linkedin_autoposter.py authorize
    python tools/linkedin_autoposter.py seed
    python tools/linkedin_autoposter.py run

`run` is a long-running scheduler. Keep that one command running and posts in
linkedin_posts.json will publish automatically at their `scheduled_at` time.
It only creates posts; it never sends connection requests, DMs, or scrapes
LinkedIn profiles.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / ".linkedin.env"
TOKEN_PATH = ROOT / ".linkedin_token.json"
POSTS_PATH = ROOT / "linkedin_posts.json"
CURATED_POSTS_PATH = ROOT / "linkedin_curated_posts.json"
HISTORY_PATH = ROOT / "linkedin_post_history.json"
IST = ZoneInfo("Asia/Kolkata")

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
DEFAULT_API_VERSION = "202606"


def read_env(path: Path) -> dict[str, str]:
    """Read a deliberately small KEY=value env file without dependencies."""
    values = dict(os.environ)
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def required_config(env: dict[str, str]) -> tuple[str, str, str]:
    fields = ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI")
    missing = [field for field in fields if not env.get(field)]
    if missing:
        raise RuntimeError(
            "Missing " + ", ".join(missing) + ". Copy tools/.linkedin.env.example "
            "to tools/.linkedin.env and fill in the values from LinkedIn Developer Portal."
        )
    return tuple(env[field] for field in fields)  # type: ignore[return-value]


def request_json(url: str, *, method: str = "GET", data: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> dict[str, Any]:
    body: bytes | None = None
    request_headers = dict(headers or {})
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LinkedIn API returned HTTP {exc.code}: {detail}") from exc


def token_request(data: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LinkedIn token request failed (HTTP {exc.code}): {detail}") from exc


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path.name}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def get_token() -> dict[str, Any]:
    token = load_json(TOKEN_PATH, {})
    if not token.get("access_token") or not token.get("person_urn"):
        raise RuntimeError("Not authorized. Run: python tools/linkedin_autoposter.py authorize")
    return token


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    expected_state = ""
    result: dict[str, str] = {}
    completed = threading.Event()

    def do_GET(self) -> None:  # noqa: N802 - HTTP handler contract
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        state = params.get("state", [""])[0]
        if state != self.expected_state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid OAuth state. You can close this tab.")
            self.result = {"error": "OAuth state did not match"}
        elif params.get("error"):
            self.send_response(400)
            self.end_headers()
            message = params.get("error_description", params["error"])[0]
            self.wfile.write(b"Authorization was not completed. You can close this tab.")
            self.result = {"error": message}
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>SkillMe LinkedIn authorization completed.</h2><p>You may close this tab.</p>")
            self.result = {"code": params.get("code", [""])[0]}
        self.completed.set()

    def log_message(self, format: str, *args: Any) -> None:
        return


def authorize(env: dict[str, str]) -> None:
    client_id, client_secret, redirect_uri = required_config(env)
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.port:
        raise RuntimeError(
            "For this one-file local setup, LINKEDIN_REDIRECT_URI must use localhost with a port, "
            "for example http://localhost:8765/callback. Add that exact URL in LinkedIn Developer Portal first."
        )

    state = secrets.token_urlsafe(32)
    OAuthCallbackHandler.expected_state = state
    OAuthCallbackHandler.result = {}
    OAuthCallbackHandler.completed.clear()

    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile w_member_social",
    })
    callback_server = ThreadingHTTPServer((parsed.hostname, parsed.port), OAuthCallbackHandler)
    threading.Thread(target=callback_server.handle_request, daemon=True).start()
    print("Opening LinkedIn. Sign in and approve the official posting permission...")
    webbrowser.open(f"{AUTH_URL}?{query}")

    if not OAuthCallbackHandler.completed.wait(timeout=300):
        callback_server.server_close()
        raise RuntimeError("Timed out waiting for LinkedIn authorization. Try authorize again.")
    callback_server.server_close()

    if "error" in OAuthCallbackHandler.result:
        raise RuntimeError(f"Authorization failed: {OAuthCallbackHandler.result['error']}")
    code = OAuthCallbackHandler.result.get("code")
    if not code:
        raise RuntimeError("LinkedIn did not return an authorization code.")

    token = token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })
    user = request_json(USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"})
    person_id = user.get("sub")
    if not person_id:
        raise RuntimeError("LinkedIn did not return your member ID. Check that OpenID Connect is enabled for the app.")
    token["person_urn"] = f"urn:li:person:{person_id}"
    token["authorized_at"] = datetime.now(IST).isoformat()
    write_json(TOKEN_PATH, token)
    print("Authorized successfully. Your token was saved locally and is excluded from git.")


def publish(post: dict[str, Any], env: dict[str, str]) -> str:
    token = get_token()
    text = str(post.get("text", "")).strip()
    if not text:
        raise RuntimeError(f"Post {post.get('id', '<unknown>')} has no text.")
    if len(text) > 3000:
        raise RuntimeError(f"Post {post.get('id', '<unknown>')} is over LinkedIn's 3,000-character limit.")

    payload = {
        "author": token["person_urn"],
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    response = request_json(
        POSTS_URL,
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Linkedin-Version": env.get("LINKEDIN_API_VERSION", DEFAULT_API_VERSION),
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    return str(response.get("id", response.get("urn", "posted")))


def parse_scheduled_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def run_due_posts(env: dict[str, str], *, dry_run: bool = False) -> int:
    posts = load_json(POSTS_PATH, [])
    if not isinstance(posts, list):
        raise RuntimeError("linkedin_posts.json must be a JSON array.")
    history = load_json(HISTORY_PATH, {})
    now = datetime.now(IST)
    published = 0

    for post in posts:
        post_id = str(post.get("id", ""))
        if not post_id or post_id in history:
            continue
        scheduled_at = parse_scheduled_at(str(post.get("scheduled_at", "")))
        if scheduled_at > now:
            continue
        if post.get("enabled", True) is False:
            continue
        if dry_run:
            print(f"Would publish {post_id} at {scheduled_at.isoformat()}: {post.get('text', '')[:80]}...")
            published += 1
            continue
        try:
            linkedin_id = publish(post, env)
        except Exception as exc:
            print(f"Failed to publish {post_id}: {exc}", file=sys.stderr)
            continue
        history[post_id] = {
            "published_at": datetime.now(IST).isoformat(),
            "linkedin_post_id": linkedin_id,
            "scheduled_at": scheduled_at.isoformat(),
        }
        write_json(HISTORY_PATH, history)
        published += 1
        print(f"Published {post_id}: {linkedin_id}")
    return published


def seed_posts() -> None:
    if POSTS_PATH.exists():
        raise RuntimeError("linkedin_posts.json already exists. Edit it directly instead of overwriting it.")
    curated_posts = load_json(CURATED_POSTS_PATH, [])
    if not isinstance(curated_posts, list) or not curated_posts:
        raise RuntimeError("linkedin_curated_posts.json must contain at least one curated post.")
    tomorrow = (datetime.now(IST) + timedelta(days=1)).date()
    scheduled: list[dict[str, Any]] = []
    for index, item in enumerate(curated_posts):
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            raise RuntimeError(f"Curated post at position {index + 1} is missing text.")
        day = tomorrow + timedelta(days=index // 2)
        hour, minute = (10, 0) if index % 2 == 0 else (18, 30)
        scheduled.append({
            "id": f"{item.get('id', f'curated-{index + 1:03d}')}-{day.isoformat()}",
            "scheduled_at": datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).isoformat(),
            "text": item["text"],
            "enabled": True,
        })
    write_json(POSTS_PATH, scheduled)
    print(f"Created {len(scheduled)} scheduled posts in {POSTS_PATH.name}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("authorize", "seed", "once", "run", "dry-run"))
    parser.add_argument("--interval", type=int, default=60, help="Polling interval for run mode, in seconds (default: 60).")
    args = parser.parse_args()
    env = read_env(CONFIG_PATH)

    if args.command == "authorize":
        authorize(env)
    elif args.command == "seed":
        seed_posts()
    elif args.command == "dry-run":
        run_due_posts(env, dry_run=True)
    elif args.command == "once":
        count = run_due_posts(env)
        print(f"Published {count} due post(s).")
    else:
        print("SkillMe LinkedIn autoposter is running. Press Ctrl+C to stop.")
        try:
            while True:
                run_due_posts(env)
                time.sleep(max(args.interval, 15))
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
