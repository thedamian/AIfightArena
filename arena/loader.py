"""Watches /player and keeps the set of loaded fighter scripts in sync.

Poll-based on purpose: it is a handful of small files, and polling avoids a
platform-specific filesystem-watcher dependency while behaving identically on
every OS. Adding, editing or deleting a file in /player takes effect in the
running match within a second.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .sandbox import LoadedScript, ScriptError, load_script


@dataclass
class Changes:
    added: list[LoadedScript] = field(default_factory=list)
    reloaded: list[LoadedScript] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    def any(self) -> bool:
        return bool(self.added or self.reloaded or self.removed or self.failed)


class PlayerLoader:
    def __init__(self, directory: Path, poll_interval: float = 0.75):
        self.directory = Path(directory)
        self.poll_interval = poll_interval
        self.scripts: dict[str, LoadedScript] = {}
        self.errors: dict[str, str] = {}
        self._stamps: dict[str, tuple[float, int]] = {}
        self._last_poll = 0.0

    # ------------------------------------------------------------------ api
    def poll(self, force: bool = False) -> Changes:
        now = time.monotonic()
        if not force and now - self._last_poll < self.poll_interval:
            return Changes()
        self._last_poll = now
        return self.scan()

    def scan(self) -> Changes:
        changes = Changes()
        seen: set[str] = set()

        for path in sorted(self.directory.glob("*.py")):
            filename = path.name
            if filename.startswith("_"):
                continue
            seen.add(filename)

            try:
                stat = path.stat()
            except OSError:
                continue
            stamp = (stat.st_mtime, stat.st_size)
            if self._stamps.get(filename) == stamp:
                continue
            self._stamps[filename] = stamp

            is_new = filename not in self.scripts
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as e:
                changes.failed[filename] = f"could not read file: {e}"
                self.errors[filename] = changes.failed[filename]
                continue

            try:
                script = load_script(path, source, seed=abs(hash(filename)) % 100_000)
            except ScriptError as e:
                message = str(e)
                changes.failed[filename] = message
                self.errors[filename] = message
                # A file that used to work but no longer compiles keeps its old
                # brain rather than yanking a fighter mid-match.
                continue

            self.errors.pop(filename, None)
            self.scripts[filename] = script
            (changes.added if is_new else changes.reloaded).append(script)

        for filename in list(self.scripts):
            if filename not in seen:
                del self.scripts[filename]
                self._stamps.pop(filename, None)
                self.errors.pop(filename, None)
                changes.removed.append(filename)

        for filename in list(self.errors):
            if filename not in seen:
                self.errors.pop(filename, None)
                self._stamps.pop(filename, None)

        return changes

    def status(self) -> list[dict]:
        """Renderer-friendly summary of what is loaded and what is broken."""
        out = [
            {
                "file": s.filename,
                "name": s.name,
                "character": s.character_id,
                "ok": not s.disabled,
                "error": s.error,
            }
            for s in self.scripts.values()
        ]
        out.extend(
            {"file": f, "name": f, "character": None, "ok": False, "error": e}
            for f, e in self.errors.items()
        )
        return out
