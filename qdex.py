#!/usr/bin/env python3
"""Qdex: a keyboard-first terminal launcher for macOS."""

from __future__ import annotations

import curses
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "qdex"
CONFIG_FILE = CONFIG_DIR / "config.json"
VERSION = "1.0.0"


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path
    is_dir: bool = False
    is_app: bool = False


@dataclass(frozen=True)
class Settings:
    name: str
    start_directory: Path


def load_settings(config_file: Path | None = None) -> Settings | None:
    config_file = config_file or CONFIG_FILE
    if not config_file.exists():
        return None
    try:
        raw = json.loads(config_file.read_text(encoding="utf-8"))
        name = raw["name"]
        start_directory = Path(raw["start_directory"]).expanduser()
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read Qdex setup at {config_file}: {error}") from error
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid name in Qdex setup: {config_file}")
    if not start_directory.is_dir():
        raise ValueError(f"Starting folder in Qdex setup is unavailable: {start_directory}")
    return Settings(name.strip(), start_directory.resolve())


def save_settings(settings: Settings, config_file: Path | None = None) -> None:
    config_file = config_file or CONFIG_FILE
    config_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "name": settings.name,
                "start_directory": str(settings.start_directory),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(config_file)


def _read_setup_line(screen: curses.window, y: int, prompt: str, default: str) -> str:
    height, width = screen.getmaxyx()
    screen.move(y, 3)
    screen.clrtoeol()
    screen.addnstr(y, 3, f"{prompt} [{default}]: ", max(0, width - 7), curses.color_pair(4))
    screen.refresh()
    curses.echo()
    curses.curs_set(1)
    try:
        input_x = min(width - 2, 7 + len(prompt) + len(default))
        raw = screen.getstr(y, input_x, max(1, width - input_x - 2))
        value = raw.decode("utf-8").strip()
        return value or default
    finally:
        curses.noecho()
        curses.curs_set(0)


def first_run_setup(screen: curses.window) -> Settings:
    height, width = screen.getmaxyx()
    while True:
        screen.erase()
        Qdex._center_on(screen, max(1, height // 2 - 6), "Q D E X", curses.color_pair(1) | curses.A_BOLD)
        Qdex._center_on(screen, max(2, height // 2 - 4), "FIRST-TIME SYSTEM SETUP", curses.color_pair(2) | curses.A_BOLD)
        Qdex._center_on(screen, max(3, height // 2 - 2), "Personalize your terminal. Press Enter to use a default.", curses.A_DIM)
        center = max(5, height // 2)
        name = _read_setup_line(screen, center, "What should Qdex call you?", "Arda")
        folder_text = _read_setup_line(
            screen,
            min(height - 2, center + 2),
            "Starting folder",
            str(Path.home()),
        )
        folder = Path(folder_text).expanduser()
        if folder.is_dir():
            return Settings(name, folder.resolve())
        screen.move(min(height - 3, center + 4), 3)
        screen.clrtoeol()
        screen.addnstr(
            min(height - 3, center + 4),
            3,
            f"That folder does not exist: {folder}. Try again.",
            max(0, width - 6),
            curses.color_pair(5) | curses.A_BOLD,
        )
        screen.refresh()
        screen.timeout(-1)
        screen.getch()
        screen.timeout(120)


def fuzzy_score(query: str, candidate: str) -> int | None:
    """Score a subsequence match; contiguous and earlier matches rank higher."""
    query = query.casefold()
    candidate = candidate.casefold()
    if not query:
        return 0

    positions: list[int] = []
    cursor = 0
    for char in query:
        position = candidate.find(char, cursor)
        if position < 0:
            return None
        positions.append(position)
        cursor = position + 1

    gaps = positions[-1] - positions[0] + 1 - len(query)
    boundary_bonus = 8 if positions[0] == 0 or candidate[positions[0] - 1] in " /-_." else 0
    return 100 - gaps * 4 - positions[0] + boundary_bonus


def list_directory(directory: Path, query: str = "") -> list[Entry]:
    entries: list[tuple[int, Entry]] = []
    for path in directory.iterdir():
        if path.name.startswith(".") and not query.startswith("."):
            continue
        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False
        score = fuzzy_score(query, path.name)
        if score is not None:
            entries.append((score, Entry(path.name, path, is_dir=is_dir)))
    entries.sort(key=lambda item: (-int(item[1].is_dir), -item[0], item[1].name.casefold()))
    return [entry for _, entry in entries]


def list_apps(query: str = "") -> list[Entry]:
    roots = (
        Path("/Applications"),
        Path("/System/Applications"),
        Path.home() / "Applications",
    )
    apps: dict[str, Entry] = {}
    for root in roots:
        try:
            for path in root.iterdir():
                if path.suffix.casefold() != ".app" or not path.is_dir():
                    continue
                score = fuzzy_score(query, path.stem)
                if score is not None:
                    apps.setdefault(
                        str(path.resolve()),
                        Entry(path.stem, path, is_app=True),
                    )
        except OSError:
            continue
    return sorted(apps.values(), key=lambda entry: (entry.name.casefold(), str(entry.path)))


def transfer_item(source: Path, destination_directory: Path, move: bool = False) -> Path:
    source = source.expanduser()
    destination_directory = destination_directory.expanduser()
    if not source.exists() and not source.is_symlink():
        raise FileNotFoundError(f"Item no longer exists: {source}")
    if not destination_directory.is_dir():
        raise NotADirectoryError(f"Destination is not a folder: {destination_directory}")

    target = destination_directory / source.name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"An item named {source.name!r} already exists there")
    if source.resolve() == destination_directory.resolve():
        raise ValueError("Choose a different destination folder")
    if source.is_dir() and not source.is_symlink():
        try:
            destination_directory.resolve().relative_to(source.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("A folder cannot be copied or moved inside itself")

    if move:
        shutil.move(str(source), str(target))
    elif source.is_symlink():
        shutil.copy2(source, target, follow_symlinks=False)
    elif source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return target


def launch(entry: Entry) -> None:
    if entry.is_app:
        subprocess.run(["open", "-a", str(entry.path)], check=True, timeout=10)
    else:
        subprocess.run(["open", str(entry.path)], check=True, timeout=10)


class Qdex:
    def __init__(self, screen: curses.window, settings: Settings | None = None) -> None:
        self.screen = screen
        self.settings = settings or Settings("Arda", Path.home())
        self.directory = self.settings.start_directory
        self.apps_mode = False
        self.query = ""
        self.selected = 0
        self.offset = 0
        self.status = "Ready. Type to search, or use the arrow keys to explore."
        self.status_is_error = False
        self.running = True
        self.entries: list[Entry] = []
        self.refresh()

    def refresh(self) -> None:
        try:
            self.entries = list_apps(self.query) if self.apps_mode else list_directory(
                self.directory, self.query
            )
        except OSError as error:
            self.entries = []
            self.set_status(f"Can't read folder: {error}", error=True)
        self.selected = min(self.selected, max(0, len(self.entries) - 1))

    def set_status(self, message: str, error: bool = False) -> None:
        self.status = message
        self.status_is_error = error

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 12 or width < 48:
            self._put(0, 0, "QDEX needs a terminal at least 48 columns by 12 rows.")
            self.screen.refresh()
            return

        if width >= 96 and height >= 24:
            self._draw_dashboard(height, width)
        else:
            self._draw_compact(height, width)
        self.screen.refresh()

    def _draw_dashboard(self, height: int, width: int) -> None:
        dim = curses.A_DIM
        accent = curses.color_pair(1) | curses.A_BOLD
        self._put(0, 2, "Q D E X   //   NEON FILE SYSTEM", accent)
        self._put(0, width - 23, f"ONLINE  {datetime.now():%H:%M:%S}", curses.color_pair(3) | curses.A_BOLD)
        self.screen.hline(1, 2, curses.ACS_HLINE, width - 4)

        logo = (
            " QQQQ   DDDD   EEEE   X  X ",
            "Q    Q  D   D  E       XX  ",
            "Q    Q  D   D  EEE      X   ",
            "Q   QQ  D   D  E       XX  ",
            " QQQ Q  DDDD   EEEE   X  X ",
        )
        logo_style = curses.color_pair(1) | curses.A_BOLD
        for offset, line in enumerate(logo):
            self._center(2 + offset, line, logo_style)
        self._center(7, f"HI, MR {self.settings.name.upper()}  /  YOUR MAC, AT FULL SPEED",
                     curses.color_pair(2) | curses.A_BOLD)
        self._center(8, "LIVE FILE SYSTEM  •  INSTANT SEARCH  •  ZERO FRICTION", dim)

        panel_y = 10
        panel_h = height - 14
        left_x, left_w = 1, 22
        right_x, right_w = width - 25, 24
        center_x = left_x + left_w + 1
        center_w = right_x - center_x - 1
        self._panel(panel_y, left_x, panel_h, left_w, "SYSTEM")
        self._panel(panel_y, center_x, panel_h, center_w,
                    "APP GRID" if self.apps_mode else "FILE SYSTEM")
        self._panel(panel_y, right_x, panel_h, right_w, "INSPECTOR")
        self._draw_system_panel(panel_y + 1, left_x + 2, left_w - 4)
        self._draw_main_panel(panel_y, center_x, center_w, panel_h, width)
        self._draw_inspector(panel_y + 1, right_x + 2, right_w - 4)

        self.screen.hline(height - 4, 2, curses.ACS_HLINE, width - 4)
        status_style = curses.color_pair(5) | curses.A_BOLD if self.status_is_error else curses.color_pair(1)
        self._put(height - 3, 2, f"›  {self.status}", status_style, width - 4)
        self._put(height - 2, 2,
                  "↑↓ MOVE   ↵ OPEN   TAB APPS   F5 COPY   F6 MOVE   ESC CLEAR   F10 EXIT",
                  curses.color_pair(3) | curses.A_BOLD, width - 4)

    def _draw_system_panel(self, y: int, x: int, available: int) -> None:
        fields = (
            ("HOST", platform.node() or "MAC"),
            ("USER", getpass.getuser()),
            ("SHELL", Path(os.environ.get("SHELL", "/bin/zsh")).name),
            ("MODE", "APP SEARCH" if self.apps_mode else "BROWSE"),
            ("ITEMS", str(len(self.entries))),
        )
        for offset, (label, value) in enumerate(fields):
            self._put(y + offset, x, f"{label:<5} {value}",
                      curses.color_pair(3) if label == "MODE" else curses.color_pair(4),
                      available)
        if y + len(fields) + 1 < self.screen.getmaxyx()[0] - 4:
            path_text = "APPS" if self.apps_mode else str(self.directory)
            self._put(y + len(fields) + 1, x, "ROOT", curses.color_pair(1) | curses.A_BOLD, available)
            self._put(y + len(fields) + 2, x, path_text, curses.A_DIM, available)

    def _draw_main_panel(self, panel_y: int, x: int, panel_w: int, panel_h: int,
                         screen_width: int) -> None:
        inner_x = x + 2
        inner_w = panel_w - 4
        mode = "APPLICATIONS" if self.apps_mode else "FILES"
        path = "Installed apps" if self.apps_mode else str(self.directory)
        self._put(panel_y + 1, inner_x, f"[{mode}] {path}", curses.color_pair(4), inner_w)
        self._put(panel_y + 2, inner_x, "SEARCH  >", curses.color_pair(2) | curses.A_BOLD,
                  min(11, inner_w))
        self._put(panel_y + 2, inner_x + 11, self.query or "type anything...",
                  curses.color_pair(4) if self.query else curses.A_DIM,
                  max(0, inner_w - 11))
        self.screen.hline(panel_y + 3, x + 1, curses.ACS_HLINE, panel_w - 2)

        list_top = panel_y + 4
        list_bottom = panel_y + panel_h - 1
        visible = max(0, list_bottom - list_top)
        if self.selected < self.offset:
            self.offset = self.selected
        elif self.selected >= self.offset + visible and visible:
            self.offset = self.selected - visible + 1

        if not self.entries:
            self._put(list_top + 1, inner_x, "NO MATCHES  /  ADJUST SEARCH",
                      curses.A_DIM, inner_w)
            return
        for row, index in enumerate(range(self.offset, min(len(self.entries), self.offset + visible))):
            entry = self.entries[index]
            selected = index == self.selected
            marker = ">" if selected else " "
            icon = "[DIR]" if entry.is_dir else "[APP]" if entry.is_app else "[FILE]"
            style = curses.color_pair(2) | curses.A_BOLD if selected else curses.color_pair(4)
            self._put(list_top + row, inner_x, f"{marker} {icon}  {entry.name}", style, inner_w)

    def _draw_inspector(self, y: int, x: int, available: int) -> None:
        if self.apps_mode:
            self._put(y, x, "APP LAUNCHER", curses.color_pair(3) | curses.A_BOLD, available)
            self._put(y + 2, x, "Enter to launch", curses.color_pair(4), available)
            self._put(y + 3, x, "Tab for files", curses.A_DIM, available)
        elif self.entries:
            entry = self.entries[self.selected]
            kind = "FOLDER" if entry.is_dir else "FILE"
            self._put(y, x, f"SELECTED // {kind}", curses.color_pair(3) | curses.A_BOLD, available)
            self._put(y + 2, x, entry.name, curses.color_pair(4) | curses.A_BOLD, available)
            self._put(y + 4, x, "LOCATION", curses.color_pair(1) | curses.A_BOLD, available)
            self._put(y + 5, x, str(entry.path.parent), curses.A_DIM, available)
            if not entry.is_dir:
                try:
                    size = entry.path.stat().st_size
                    size_label = f"{size:,} bytes"
                except OSError:
                    size_label = "Unavailable"
                self._put(y + 7, x, f"SIZE  {size_label}", curses.color_pair(1), available)
        else:
            self._put(y, x, "NOTHING SELECTED", curses.A_DIM, available)

    def _draw_compact(self, height: int, width: int) -> None:
        self._put(0, 2, "Q D E X  //  MACOS SYSTEM NAVIGATOR",
                  curses.color_pair(1) | curses.A_BOLD, width - 4)
        self.screen.hline(1, 2, curses.ACS_HLINE, width - 4)
        self._center(2, "Q D E X", curses.color_pair(1) | curses.A_BOLD)
        self._center(3, f"HI, MR {self.settings.name.upper()}  /  MOVE THROUGH YOUR MAC",
                     curses.color_pair(2) | curses.A_BOLD)
        mode = "APPLICATIONS" if self.apps_mode else "FILES"
        path = "Installed apps" if self.apps_mode else str(self.directory)
        self._put(5, 2, f"[{mode}] {path}", curses.color_pair(3) | curses.A_BOLD, width - 4)
        self._put(6, 2, "SEARCH >", curses.color_pair(2) | curses.A_BOLD)
        self._put(6, 11, self.query or "type anything...", curses.color_pair(4), width - 13)

        list_top = 8
        list_bottom = height - 4
        visible = max(1, list_bottom - list_top)
        if self.selected < self.offset:
            self.offset = self.selected
        elif self.selected >= self.offset + visible:
            self.offset = self.selected - visible + 1
        if not self.entries:
            self._put(list_top, 4, "NO MATCHES  /  ADJUST SEARCH", curses.A_DIM, width - 8)
        else:
            for row, index in enumerate(range(self.offset, min(len(self.entries), self.offset + visible))):
                entry = self.entries[index]
                marker = ">" if index == self.selected else " "
                icon = "[DIR]" if entry.is_dir else "[APP]" if entry.is_app else "[FILE]"
                style = curses.color_pair(2) | curses.A_BOLD if index == self.selected else curses.color_pair(4)
                self._put(list_top + row, 3, f"{marker} {icon}  {entry.name}", style, width - 6)
        self.screen.hline(height - 3, 2, curses.ACS_HLINE, width - 4)
        status_style = curses.color_pair(5) if self.status_is_error else curses.color_pair(4)
        self._put(height - 2, 2, self.status, status_style, width - 4)
        self._put(height - 1, 2, "↑↓ NAV   ↵ OPEN   TAB APPS   F5 COPY   F6 MOVE   F10 EXIT",
                  curses.color_pair(3) | curses.A_BOLD, width - 4)

    def _panel(self, y: int, x: int, height: int, width: int, title: str) -> None:
        self.screen.attron(curses.color_pair(1) | curses.A_DIM)
        self.screen.addch(y, x, curses.ACS_ULCORNER)
        self.screen.addch(y, x + width - 1, curses.ACS_URCORNER)
        self.screen.addch(y + height - 1, x, curses.ACS_LLCORNER)
        self.screen.addch(y + height - 1, x + width - 1, curses.ACS_LRCORNER)
        self.screen.hline(y, x + 1, curses.ACS_HLINE, width - 2)
        self.screen.hline(y + height - 1, x + 1, curses.ACS_HLINE, width - 2)
        self.screen.vline(y + 1, x, curses.ACS_VLINE, height - 2)
        self.screen.vline(y + 1, x + width - 1, curses.ACS_VLINE, height - 2)
        self.screen.attroff(curses.color_pair(1) | curses.A_DIM)
        self._put(y, x + 2, f" {title} ", curses.color_pair(1) | curses.A_BOLD, width - 4)

    def _put(self, y: int, x: int, text: str, style: int = 0, limit: int | None = None) -> None:
        height, width = self.screen.getmaxyx()
        if y < 0 or y >= height or x < 0 or x >= width:
            return
        count = width - x - 1
        if limit is not None:
            count = min(count, limit)
        if count > 0 and text:
            self.screen.addnstr(y, x, text, count, style)

    def _center(self, row: int, text: str, style: int = 0) -> None:
        width = self.screen.getmaxyx()[1]
        x = max(0, (width - len(text)) // 2)
        self._put(row, x, text, style)

    @staticmethod
    def _center_on(screen: curses.window, row: int, text: str, style: int = 0) -> None:
        width = screen.getmaxyx()[1]
        x = max(0, (width - len(text)) // 2)
        screen.addnstr(row, x, text, max(0, width - x - 1), style)

    def _destination_prompt(self, action: str) -> str | None:
        height, width = self.screen.getmaxyx()
        prompt = f"{action} to folder (path, ~ allowed): "
        self.screen.move(height - 2, 2)
        self.screen.clrtoeol()
        self.screen.addnstr(height - 2, 2, prompt, width - 4, curses.color_pair(2) | curses.A_BOLD)
        curses.echo()
        curses.curs_set(1)
        self.screen.timeout(-1)
        try:
            self.screen.refresh()
            raw = self.screen.getstr(height - 2, min(width - 3, 2 + len(prompt)), max(1, width - len(prompt) - 5))
            return raw.decode("utf-8").strip() or None
        finally:
            curses.noecho()
            curses.curs_set(0)
            self.screen.timeout(120)

    def _transfer(self, move: bool) -> None:
        if self.apps_mode or not self.entries:
            self.set_status("Copy and move are available for files and folders.", error=True)
            return
        destination = self._destination_prompt("Move" if move else "Copy")
        if destination is None:
            self.set_status("Cancelled.")
            return
        try:
            target = transfer_item(
                self.entries[self.selected].path,
                Path(destination),
                move=move,
            )
        except (OSError, ValueError) as error:
            self.set_status(str(error), error=True)
            return
        self.set_status(f"{'Moved' if move else 'Copied'} to {target}")
        if move:
            self.refresh()

    def handle_key(self, key: int) -> None:
        if key in (curses.KEY_UP, ord("k")):
            self.selected = max(0, self.selected - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.selected = min(max(0, len(self.entries) - 1), self.selected + 1)
        elif key == curses.KEY_PPAGE:
            self.selected = max(0, self.selected - 10)
        elif key == curses.KEY_NPAGE:
            self.selected = min(max(0, len(self.entries) - 1), self.selected + 10)
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.entries:
                entry = self.entries[self.selected]
                try:
                    if entry.is_dir and not entry.is_app:
                        self.directory = entry.path
                        self.query = ""
                        self.selected = self.offset = 0
                        self.refresh()
                        self.set_status(f"Opened folder: {self.directory}")
                    else:
                        launch(entry)
                        self.set_status(f"Opened {entry.name}")
                except (OSError, subprocess.SubprocessError) as error:
                    self.set_status(f"Couldn't open {entry.name}: {error}", error=True)
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.query:
                self.query = self.query[:-1]
                self.selected = 0
                self.refresh()
            elif not self.apps_mode and self.directory.parent != self.directory:
                self.directory = self.directory.parent
                self.selected = self.offset = 0
                self.refresh()
                self.set_status(f"Opened folder: {self.directory}")
        elif key == 27:
            if self.query:
                self.query = ""
                self.selected = self.offset = 0
                self.refresh()
            else:
                self.set_status("Search cleared.")
        elif key == 9:
            self.apps_mode = not self.apps_mode
            self.query = ""
            self.selected = self.offset = 0
            self.refresh()
            self.set_status("Search installed apps." if self.apps_mode else f"Browsing {self.directory}")
        elif key in (curses.KEY_F5, curses.KEY_F6):
            self._transfer(move=key == curses.KEY_F6)
        elif key == curses.KEY_F10:
            self.running = False
        elif 32 <= key <= 126:
            self.query += chr(key)
            self.selected = self.offset = 0
            self.refresh()
            self.set_status(f"{len(self.entries)} match{'es' if len(self.entries) != 1 else ''}.")

    def run(self) -> None:
        self.screen.keypad(True)
        self.screen.timeout(120)
        curses.curs_set(0)
        while self.running:
            self.draw()
            key = self.screen.getch()
            if key != -1:
                self.handle_key(key)


def _configure_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_MAGENTA, -1)
    curses.init_pair(3, curses.COLOR_GREEN, -1)
    curses.init_pair(4, curses.COLOR_WHITE, -1)
    curses.init_pair(5, curses.COLOR_RED, -1)


def main() -> int:
    if sys.argv[1:] in (["--help"], ["-h"]):
        print(
            "Qdex — keyboard-first neon terminal launcher for macOS\n"
            "\n"
            "Run `qdex` to browse files or press Tab to search installed apps.\n"
            "First launch asks for your display name and starting folder.\n"
            "\n"
            "Keys: arrows navigate, Enter open, Tab apps, F5 copy, F6 move,\n"
            "      Backspace parent folder, Esc clear search, F10 quit."
        )
        return 0
    if sys.argv[1:] == ["--version"]:
        print(f"Qdex {VERSION}")
        return 0
    if sys.platform != "darwin":
        print("Qdex currently supports macOS only.", file=sys.stderr)
        return 1

    def run(screen: curses.window) -> None:
        _configure_colors()
        try:
            settings = load_settings()
            if settings is None:
                settings = first_run_setup(screen)
                save_settings(settings)
        except (OSError, ValueError) as error:
            screen.erase()
            screen.addnstr(1, 2, f"Qdex setup failed: {error}", max(1, screen.getmaxyx()[1] - 4))
            screen.addnstr(3, 2, "Fix the setup file or permissions, then try again.", max(1, screen.getmaxyx()[1] - 4))
            screen.addnstr(5, 2, "Press any key to exit.", max(1, screen.getmaxyx()[1] - 4))
            screen.refresh()
            screen.getch()
            return
        Qdex(screen, settings).run()

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
