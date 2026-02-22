import os
import tempfile
from typing import Iterator
from contextlib import contextmanager

@contextmanager
def named_tempfile(suffix: str):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
