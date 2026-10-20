"""Atomic local report output; no broker/GUI/network dependencies.

Protects known input aliases (including hard links), never follows an output
symlink, and publishes only a fully written UTF-8 file. This is not a sandbox
against someone who can mutate parent directories concurrently. Use trusted
local directories; network filesystems and power-loss recovery are untested.
"""
from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Iterable


def validate_output(path: str | Path, *, overwrite: bool = False,
                    protected: Iterable[str | Path] = ()) -> Path:
    """Refuse input aliases, non-files, symlinks and implicit overwrites."""
    if type(overwrite) is not bool:
        raise ValueError("overwrite must be a boolean")
    output = Path(path)
    if not output.parent.is_dir():
        raise ValueError("output parent directory must already exist")
    if output.is_symlink():
        raise ValueError("output symlinks are not supported")
    resolved = output.resolve()
    for original in protected:
        source = Path(original)
        if resolved == source.resolve() or (
            output.exists() and source.exists() and output.samefile(source)
        ):
            raise ValueError("output must not overwrite an input or registry file")
    if output.exists():
        if not stat.S_ISREG(output.stat().st_mode):
            raise ValueError("output must be a regular file")
        if not overwrite:
            raise FileExistsError("output already exists; use --overwrite explicitly")
    return output


def atomic_write_text(path: str | Path, text: str, *, overwrite: bool = False,
                      protected: Iterable[str | Path] = ()) -> None:
    """Write in the same directory, fsync, then publish without partial reports.

    No-overwrite publication uses an atomic hard link. A filesystem without
    hard-link support fails closed; it does not fall back to a racy overwrite.
    Existing reports are replaced only with explicit overwrite=True.
    """
    if type(text) is not str:
        raise ValueError("report must be a string")
    payload = text.encode("utf-8")
    sources = tuple(protected)
    output = validate_output(path, overwrite=overwrite, protected=sources)
    fd, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp",
                                dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck input aliases and output collisions after expensive work.
        validate_output(output, overwrite=overwrite, protected=sources)
        if overwrite:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)
        # Directory fsync is best effort; not supported on every OS/filesystem.
        if os.name == "posix":
            with suppress(OSError):
                directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()
