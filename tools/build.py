#!/usr/bin/env python3
"""Builds board.html, a single self-contained page, from board.json and the template.

Usage:
    python3 tools/build.py                 the page with the board that sits beside this folder
    python3 tools/build.py --empty <file>  a page with no data, for the app that is shared
"""
import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE.parent
TEMPLATE = HERE / "board.template.html"
BOARD = FOLDER / "board.json"
TICKS = FOLDER / "ticks.json"
MANUAL = FOLDER / "manual.json"
OUTPUT = FOLDER / "board.html"
OPEN_ITEMS_MD = FOLDER / "open-items.md"
LOGO = HERE / "logo.png"
# What a new user starts with besides an empty board: public reference only (projects and links).
STARTER = HERE / "starter-board.json"
# The welcome picture, and the same scene with the cat walking: a light video and, as a fallback,
# a GIF. All three are optional: a missing file simply leaves its place empty.
WELCOME_IMAGE = HERE / "welcome.jpg"
WELCOME_VIDEO = HERE / "welcome.mp4"
WELCOME_GIF = HERE / "welcome.gif"

BOARD_MARK = "__BOARD__"
LOGO_MARK = "__LOGO__"
WELCOME_IMAGE_MARK = "__WELCOME_IMAGE__"
WELCOME_VIDEO_MARK = "__WELCOME_VIDEO__"
WELCOME_GIF_MARK = "__WELCOME_GIF__"

ITEM_FIELDS = ("id", "group", "item", "openedOn", "owner")
EMPTY_BOARD = {
    "updatedOn": "",
    "nextMeeting": "to be confirmed",
    "me": "",
    "meetings": [],
    "items": [],
    "dates": [],
    "deliverables": [],
    "project": {},
}


def encoded(file: Path) -> str:
    """The file as base64 text, or nothing when the file is not there."""
    try:
        return base64.b64encode(file.read_bytes()).decode("ascii")
    except OSError:
        return ""


def data_uri(file: Path, media_type: str) -> str:
    content = encoded(file)
    return f"data:{media_type};base64,{content}" if content else ""


def check(board: dict) -> None:
    """Refuses a board the page could not show, saying what is wrong."""
    for key in ("updatedOn", "nextMeeting", "meetings", "items", "dates"):
        if key not in board:
            raise ValueError(f"board.json has no '{key}'")
    ids = [item.get("id") for item in board["items"]]
    if len(ids) != len(set(ids)):
        raise ValueError("board.json has two items with the same id")
    for item in board["items"]:
        missing = [field for field in ITEM_FIELDS if not item.get(field)]
        if missing:
            raise ValueError(f"item {item.get('id')} has no {', '.join(missing)}")
    for meeting in board["meetings"]:
        if not meeting.get("date") or not meeting.get("title") or "blocks" not in meeting:
            raise ValueError("a meeting has no date, title or blocks")


def read_json(file: Path, empty):
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty
    return value if isinstance(value, type(empty)) else empty


def with_manual_items(board: dict) -> dict:
    """Adds to the items the ones the owner entered by hand in the app (manual.json)."""
    added = [
        {
            "id": entry["id"],
            "group": "Added manually",
            "item": entry["text"],
            "openedOn": entry["date"],
            "owner": entry.get("owner") or board.get("me", ""),
            "remark": "",
        }
        for entry in read_json(MANUAL, [])
        if isinstance(entry, dict) and entry.get("type") == "item"
    ]
    return {**board, "items": [*board["items"], *added]}


def cell(text: object) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ")


def open_items_md(board: dict, ticks: dict) -> str:
    """The list of items as plain text, always in step with the board."""
    lines = [
        "# Open items",
        "",
        "Generated from `board.json` by `tools/build.py`. Do not edit by hand: edits are overwritten.",
        "",
        f"Updated: {board['updatedOn']}",
        f"Next meeting: {board['nextMeeting']}",
    ]
    done_on = {item["id"]: item.get("doneOn") or ticks.get(item["id"]) for item in board["items"]}
    groups = list(dict.fromkeys(item["group"] for item in board["items"]))
    for group in groups:
        still_open = [item for item in board["items"] if item["group"] == group and not done_on[item["id"]]]
        if not still_open:
            continue
        lines += ["", f"## Open: {group}", "", "| ID | Item | Opened | Owner | Notes |", "| --- | --- | --- | --- | --- |"]
        lines += [
            f"| {item['id']} | {cell(item['item'])} | {item['openedOn']} | {cell(item['owner'])} | {cell(item.get('remark'))} |"
            for item in still_open
        ]
    done = sorted((item for item in board["items"] if done_on[item["id"]]), key=lambda item: (done_on[item["id"]], item["id"]))
    lines += ["", "## Done", "", "| ID | Item | Done | Owner | Notes |", "| --- | --- | --- | --- | --- |"]
    lines += [
        f"| {item['id']} | {cell(item['item'])} | {done_on[item['id']]} | {cell(item['owner'])} | {cell(item.get('remark'))} |"
        for item in done
    ]
    if board["dates"]:
        lines += ["", "## Dates ahead", ""]
        lines += [f"- {entry['when']}: {entry['what']}" for entry in board["dates"]]
    return "\n".join(lines) + "\n"


def page_with(board: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(BOARD_MARK) != 1:
        raise ValueError(f"the template must have the mark {BOARD_MARK} exactly once")
    embedded = json.dumps(board, ensure_ascii=False).replace("</", "<\\/")
    return (
        template.replace(LOGO_MARK, data_uri(LOGO, "image/png"))
        .replace(WELCOME_VIDEO_MARK, encoded(WELCOME_VIDEO))
        .replace(WELCOME_GIF_MARK, data_uri(WELCOME_GIF, "image/gif"))
        .replace(WELCOME_IMAGE_MARK, data_uri(WELCOME_IMAGE, "image/jpeg"))
        .replace(BOARD_MARK, embedded)
    )


def first_board() -> dict:
    """The empty board, with the project reference of the starter file when there is one."""
    project = read_json(STARTER, {}).get("project")
    return {**EMPTY_BOARD, "project": project if isinstance(project, dict) else {}}


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--empty":
        try:
            Path(sys.argv[2]).write_text(page_with(first_board()), encoding="utf-8")
        except (OSError, ValueError) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(f"empty page at {sys.argv[2]}")
        return 0
    try:
        board = json.loads(BOARD.read_text(encoding="utf-8"))
        check(board)
        OUTPUT.write_text(page_with(board), encoding="utf-8")
        OPEN_ITEMS_MD.write_text(open_items_md(with_manual_items(board), read_json(TICKS, {})), encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"{OUTPUT.name}: {len(board['meetings'])} meetings, {len(board['items'])} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
