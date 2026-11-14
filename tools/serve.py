#!/usr/bin/env python3
"""A local test server for the board page. For development only.

The app itself runs no server: the page talks to it through a message bridge. This script stands
in for the app so the page can be opened in a browser. It listens on 127.0.0.1 only, checks the
Host and Origin of every request, and never talks to the network: the AI and the connections
answer with sample data.

Usage:
    python3 tools/serve.py [--no-open]

Environment:
    BOARD_FOLDER   folder with board.html and the board files (default: the folder beside tools/)
    BOARD_PORT     port to listen on (default: 4311)
    BOARD_FAKE_AI  set to anything to make the AI routes answer with sample entries
"""
import json
import os
import re
import sys
import tempfile
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FOLDER = Path(os.environ.get("BOARD_FOLDER") or Path(__file__).resolve().parent.parent)
HOST = "127.0.0.1"
PORT = int(os.environ.get("BOARD_PORT", "4311"))
ADDRESS = f"http://{HOST}:{PORT}/"
ALLOWED_HOSTS = (f"{HOST}:{PORT}", f"localhost:{PORT}")
ALLOWED_ORIGINS = tuple(f"http://{host}" for host in ALLOWED_HOSTS)
BODY_LIMIT = 256 * 1024
TEXT_LIMIT = 500
NOTE_LIMIT = 4000
MANUAL_TYPES = ("item", "link", "note", "decision", "date")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")

# Connections are kept in memory: nothing secret is ever written by this server.
CONNECTIONS = {"repos": [], "token": False, "calendar": False}

SAMPLE_SUGGESTIONS = [
    {"type": "item", "text": "Send the budget draft to the board", "owner": "Ana", "when": "", "url": ""},
    {"type": "decision", "text": "Launch moves to January", "owner": "", "when": "", "url": ""},
    {"type": "date", "text": "Board call", "owner": "", "when": "2027-01-15", "url": ""},
]


def read(name: str, empty):
    """One board file, or `empty` when it is missing or is not of the expected kind."""
    try:
        value = json.loads((FOLDER / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty
    except (OSError, ValueError) as error:
        raise ValueError(f"{name} cannot be read") from error
    return value if isinstance(value, type(empty)) else empty


def write(name: str, value) -> None:
    """Writes one board file atomically."""
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=FOLDER, prefix=".writing-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, FOLDER / name)
    except OSError:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def text_field(body: dict, name: str, limit: int = TEXT_LIMIT) -> str:
    value = body.get(name, "")
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"field {name} is not valid")
    return value.strip()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_note(body: dict) -> list:
    text = text_field(body, "text", NOTE_LIMIT)
    if not text:
        raise ValueError("empty note")
    notes = read("notes.json", [])
    number = 1 + max((note.get("n", 0) for note in notes if isinstance(note, dict)), default=0)
    return [*notes, {"n": number, "when": now(), "text": text, "filedOn": None}]


def edited_note(body: dict) -> list:
    text = text_field(body, "text", NOTE_LIMIT)
    notes = read("notes.json", [])
    if not text or not any(note.get("n") == body.get("n") for note in notes):
        raise ValueError("note not found or empty")
    return [{**note, "text": text, "filedOn": None} if note.get("n") == body.get("n") else note for note in notes]


def without_note(body: dict) -> list:
    notes = read("notes.json", [])
    remaining = [note for note in notes if note.get("n") != body.get("n")]
    if len(remaining) == len(notes):
        raise ValueError("note not found")
    return remaining


def new_manual(body: dict) -> list:
    kind, text = text_field(body, "type"), text_field(body, "text")
    link = text_field(body, "url")
    if kind not in MANUAL_TYPES or not text or (link and not link.startswith("https://")):
        raise ValueError("type, place or text is not valid")
    entries = read("manual.json", [])
    numbers = [int(entry["id"][1:]) for entry in entries if re.fullmatch(r"m\d+", str(entry.get("id")))]
    entry = {
        "id": f"m{1 + max(numbers, default=0)}",
        "type": kind,
        "where": text_field(body, "where"),
        "text": text,
        "url": link,
        "owner": text_field(body, "owner"),
        "when": text_field(body, "when"),
        "date": datetime.now().date().isoformat(),
    }
    return [*entries, entry]


def without_manual(body: dict) -> list:
    entries = read("manual.json", [])
    remaining = [entry for entry in entries if entry.get("id") != body.get("id")]
    if len(remaining) == len(entries):
        raise ValueError("entry not found")
    return remaining


def ai_config() -> dict:
    saved = read("ai.json", {})
    url = saved.get("url", "")
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0] if url else ""
    model = saved.get("model", "") if url else ""
    return {
        "url": url,
        "model": model,
        "format": saved.get("format", "openai") if url else "openai",
        "hasKey": False,
        "local": host in ("127.0.0.1", "localhost", ""),
        "host": host,
        "ready": bool(url and model),
    }


def save_ai_config(body: dict) -> dict:
    """Keeps the address and the model. An API key exists only in the app, in the Keychain."""
    url, model = text_field(body, "url"), text_field(body, "model", 120)
    if url and not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("use an https address, or http only for 127.0.0.1 or localhost")
    style = body.get("format") if body.get("format") in ("openai", "anthropic") else "openai"
    write("ai.json", {"url": url, "model": model, "format": style} if url else {})
    return ai_config()


def connections_config() -> dict:
    return {
        "github": {"repos": list(CONNECTIONS["repos"]), "hasToken": CONNECTIONS["token"]},
        "calendar": {"connected": CONNECTIONS["calendar"]},
    }


def save_connections_config(body: dict) -> dict:
    github, calendar = body.get("github"), body.get("calendar")
    if isinstance(github, dict):
        if github.get("disconnect") is True:
            CONNECTIONS.update(repos=[], token=False)
        else:
            if isinstance(github.get("repos"), list):
                names = [str(name).strip() for name in github["repos"] if str(name).strip()]
                if not all(REPOSITORY.match(name) for name in names) or len(names) > 12:
                    raise ValueError("write each repository as owner/name")
                CONNECTIONS["repos"] = list(dict.fromkeys(names))
            if github.get("token"):
                CONNECTIONS["token"] = True
    if isinstance(calendar, dict):
        if calendar.get("disconnect") is True:
            CONNECTIONS["calendar"] = False
        elif calendar.get("link"):
            if not str(calendar["link"]).startswith(("https://", "webcal://")):
                raise ValueError("paste the secret iCal address of the calendar (it starts with https://)")
            CONNECTIONS["calendar"] = True
    return connections_config()


def sample_github() -> dict:
    entries = []
    for repo in CONNECTIONS["repos"]:
        entries += [
            {"repo": repo, "number": 32, "title": "Support page: donation addresses",
             "url": f"https://github.com/{repo}/pull/32", "author": "ana",
             "updated": "2026-11-12T15:00:00Z", "type": "pr", "draft": True},
            {"repo": repo, "number": 41, "title": "Broken link on the team page",
             "url": f"https://github.com/{repo}/issues/41", "author": "bo",
             "updated": "2026-11-10T09:30:00Z", "type": "issue", "draft": False},
        ]
    return {"entries": entries, "errors": []}


def sample_calendar() -> dict:
    """A calendar with every shape the page's reader has to understand."""
    today = datetime.now().date()

    def day(offset: int) -> str:
        return (today + timedelta(days=offset)).strftime("%Y%m%d")

    events = [
        ["UID:a1", f"DTSTART;TZID=America/Sao_Paulo:{day(-21)}T140000", f"DTEND;TZID=America/Sao_Paulo:{day(-21)}T143000",
         "RRULE:FREQ=WEEKLY", "SUMMARY:Weekly sync\\, team", "X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij"],
        ["UID:a2", f"DTSTART:{day(0)}T210000Z", f"DTEND:{day(0)}T220000Z", "SUMMARY:Comms call", "LOCATION:Signal"],
        ["UID:a3", f"DTSTART;VALUE=DATE:{day(2)}", f"DTEND;VALUE=DATE:{day(3)}", "SUMMARY:Poll questions final"],
        ["UID:a4", f"DTSTART:{day(1)}T150000Z", f"DTEND:{day(1)}T160000Z", "SUMMARY:Cancelled one", "STATUS:CANCELLED"],
        ["UID:a5", f"DTSTART:{day(40)}T150000Z", f"DTEND:{day(40)}T160000Z", "SUMMARY:Far away"],
        ["UID:a6", f"DTSTART:{day(3)}T130000Z", f"DTEND:{day(3)}T133000Z",
         "SUMMARY:A very long title that is folded across two lines by the calendar service to", "  test unfolding"],
    ]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for event in events:
        lines += ["BEGIN:VEVENT", *event, "END:VEVENT"]
    return {"ics": "\r\n".join([*lines, "END:VCALENDAR", ""])}


def fake_ai() -> bool:
    return bool(os.environ.get("BOARD_FAKE_AI"))


def answer_get(path: str):
    if path == "/board":
        board = read("board.json", {})
        if not board:
            raise ValueError("board.json is missing or is not an object")
        return board
    if path == "/ticks":
        return read("ticks.json", {})
    if path == "/notes":
        return read("notes.json", [])
    if path == "/manual":
        return read("manual.json", [])
    if path == "/prefs":
        return read("prefs.json", {})
    if path == "/edits":
        return read("edits.json", {})
    if path == "/ai/config":
        return ai_config()
    if path == "/ai/models":
        return ["model-large", "model-small"] if fake_ai() else []
    if path == "/connections/config":
        return connections_config()
    if path == "/connections/github":
        return sample_github()
    if path == "/connections/calendar":
        return sample_calendar()
    return None


def answer_post(path: str, body):
    """Applies one write and returns what the page expects back, or None for an unknown path."""
    saved = {
        "/notes": ("notes.json", new_note),
        "/notes/edit": ("notes.json", edited_note),
        "/notes/remove": ("notes.json", without_note),
        "/manual": ("manual.json", new_manual),
        "/manual/remove": ("manual.json", without_manual),
    }
    if path in saved:
        if not isinstance(body, dict):
            raise ValueError("expected an object")
        name, change = saved[path]
        value = change(body)
        write(name, value)
        return value
    if path in ("/ticks", "/prefs", "/edits"):
        if not isinstance(body, dict):
            raise ValueError("expected an object")
        write(path[1:] + ".json", body)
        return body
    if path == "/ready":
        return {"ok": True}
    if path == "/ai/config":
        return save_ai_config(body if isinstance(body, dict) else {})
    if path == "/connections/config":
        return save_connections_config(body if isinstance(body, dict) else {})
    if path in ("/ai/suggest", "/ai/ask"):
        if not fake_ai():
            raise ValueError("the AI is only reachable from inside the app")
        if path == "/ai/suggest":
            return SAMPLE_SUGGESTIONS
        question = text_field(body, "question", 2000) if isinstance(body, dict) else ""
        size = len(str(body.get("context", ""))) if isinstance(body, dict) else 0
        return {"text": f"Example answer to: {question}\nThe board sent had {size} characters."}
    return None


class Board(BaseHTTPRequestHandler):
    server_version = "Board"

    def reply(self, status: int, body: bytes, media_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def reply_json(self, status: int, value) -> None:
        self.reply(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def host_allowed(self) -> bool:
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def do_GET(self) -> None:  # noqa: N802 (name required by the library)
        if not self.host_allowed():
            self.reply_json(403, {"error": "host not accepted"})
            return
        if self.path in ("/", "/board.html"):
            try:
                self.reply(200, (FOLDER / "board.html").read_bytes(), "text/html; charset=utf-8")
            except OSError as error:
                self.reply_json(500, {"error": f"the page could not be read: {error}"})
            return
        try:
            value = answer_get(self.path)
        except ValueError as error:
            self.reply_json(500, {"error": str(error)})
            return
        if value is None:
            self.reply_json(404, {"error": "not found"})
        else:
            self.reply_json(200, value)

    def do_POST(self) -> None:  # noqa: N802
        if not self.host_allowed() or self.headers.get("Origin", "") not in ALLOWED_ORIGINS:
            self.reply_json(403, {"error": "origin not accepted"})
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.reply_json(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= BODY_LIMIT:
                raise ValueError("body size out of bounds")
            value = answer_post(self.path, json.loads(self.rfile.read(size).decode("utf-8")))
        except ValueError as error:
            self.reply_json(400, {"error": str(error)})
            return
        except OSError as error:
            print(f"Could not write: {error}", file=sys.stderr)
            self.reply_json(500, {"error": "could not write"})
            return
        if value is None:
            self.reply_json(404, {"error": "not found"})
        else:
            self.reply_json(200, value)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (name set by the library)
        if self.command == "POST":
            sys.stderr.write(f"POST {self.path} {args[1]}\n")


def main() -> int:
    open_browser = "--no-open" not in sys.argv
    try:
        server = ThreadingHTTPServer((HOST, PORT), Board)
    except OSError:
        print(f"The board is already being served at {ADDRESS}")
        if open_browser:
            webbrowser.open(ADDRESS)
        return 0
    print(f"Board at {ADDRESS}  (close this window to stop)")
    if open_browser:
        webbrowser.open(ADDRESS)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
