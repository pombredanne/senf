# -*- coding: utf-8 -*-
# Copyright 2016 Christoph Reiter
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

import sys
import os
import ctypes

from ._fsnative import _encoding, path2fsn
from ._compat import text_type, PY2, PY3
from ._winansi import AnsiState, ansi_split
from . import _winapi as winapi


def print_(*objects, **kwargs):
    """print_(*objects, sep=None, end=None, file=None, flush=False)

    Arguments:
        objects: none or more `bytes` or `text`
        sep (fsnative): Object separator to use, defaults to ``" "``
        end (fsnative): Trailing string to use, defaults to ``"\\n"``.
            If end is ``"\\n"`` then `os.linesep` is used.
        file (object): A file-like object, defaults to `sys.stdout`
        flush (bool): If the file stream should be flushed

    A print which supports printing bytes under Unix + Python 3 and Unicode
    under Windows + Python 2.

    In addition it interprets ANSI escape sequences on platforms which
    don't support them.
    """

    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    file = kwargs.get("file", sys.stdout)
    flush = kwargs.get("flush", False)

    if end == "\n":
        end = os.linesep

    if os.name == "nt" and file in (sys.__stdout__, sys.__stderr__):
        _print_windows(objects, sep, end, file, flush)
    else:
        _print_default(objects, sep, end, file, flush)


def _print_default(objects, sep, end, file, flush):
    """A print_() implementation which writes bytes"""

    if os.name == "nt":
        encoding = "utf-8"
    else:
        encoding = _encoding()

    if isinstance(sep, text_type):
        sep = sep.encode(encoding, "replace")

    if isinstance(end, text_type):
        end = end.encode(encoding, "replace")

    parts = []
    for obj in objects:
        if isinstance(obj, text_type):
            if PY2:
                obj = obj.encode(encoding, "replace")
            else:
                obj = obj.encode(encoding, "surrogateescape")
        parts.append(obj)

    data = sep.join(parts) + end

    file = getattr(file, "buffer", file)

    try:
        file.write(data)
    except TypeError:
        if os.name != "nt" and PY3:
            # For StringIO, first try with surrogates
            surr_data = os.fsdecode(data)
            try:
                file.write(surr_data)
            except (TypeError, ValueError):
                file.write(data.decode(encoding, "replace"))
        else:
            # for file like objects with don't support bytes
            file.write(data.decode(encoding, "replace"))

    if flush:
        file.flush()


ansi_state = AnsiState()


def _print_windows(objects, sep, end, file, flush):
    """The windows implementation of print_()"""

    if file is sys.__stdout__:
        h = winapi.GetStdHandle(winapi.STD_OUTPUT_HANDLE)
    elif file is sys.__stderr__:
        h = winapi.GetStdHandle(winapi.STD_ERROR_HANDLE)
    else:
        assert 0

    if h == winapi.INVALID_HANDLE_VALUE:
        return _print_default(objects, sep, end, file, flush)

    # get the default value
    info = winapi.CONSOLE_SCREEN_BUFFER_INFO()
    if not winapi.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
        # not a console, fallback (e.g. redirect to file)
        return _print_default(objects, sep, end, file, flush)

    parts = []
    for obj in objects:
        if isinstance(obj, bytes):
            obj = obj.decode("ascii", "replace")
        if not isinstance(obj, text_type):
            obj = text_type(obj)
        parts.append(obj)

    sep = path2fsn(sep)
    end = path2fsn(end)

    text = sep.join(parts) + end
    assert isinstance(text, text_type)

    # make sure we flush before we apply any console attributes
    file.flush()

    fileno = file.fileno()

    # try to force a utf-8 code page
    old_cp = winapi.GetConsoleOutputCP()
    encoding = "utf-8"
    if winapi.SetConsoleOutputCP(65001) == 0:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        old_cp = None

    for is_ansi, part in ansi_split(text):
        if is_ansi:
            ansi_state.apply(h, part)
        else:
            os.write(fileno, part.encode(encoding, 'replace'))

    # reset the code page to what we had before
    if old_cp is not None:
        winapi.SetConsoleOutputCP(old_cp)


def input_(prompt=None):
    """
    Args:
        prompt (`bytes` or `text`): Prints the passed text to stdout without
            a trailing newline
    Returns:
        `fsnative`

    Like :func:`python3:input` but returns a `fsnative` and allows printing
    `fsnative` as prompt to stdout.

    Use :func:`fsn2text` on the output if you just want to process text.
    """

    if prompt is not None:
        print_(prompt, end="")

    data = getattr(sys.stdin, "buffer", sys.stdin).readline().rstrip(b"\r\n")
    return path2fsn(data)
