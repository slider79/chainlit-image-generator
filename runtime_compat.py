"""Repair asyncio task detection when Chainlit's CLI patches the event loop.

Chainlit's CLI calls ``nest_asyncio.apply()`` at import so the event loop can be
re-entered. To do that, nest_asyncio swaps the C implementation of
``asyncio.Task`` for the Python one. On Python 3.14 the C ``current_task()``
reads the running task from the interpreter's thread state, which only the C
task sets, so after the swap ``asyncio.current_task()`` returns ``None`` inside
a perfectly ordinary task. That breaks a chain of libraries sitting underneath
Chainlit:

    nest_asyncio  ->  asyncio.current_task() returns None
                  ->  sniffio cannot name the running async library
                  ->  anyio.to_thread.run_sync raises NoEventLoopError
                  ->  Starlette's FileResponse fails while it stats the file
                  ->  every static file is served as a 500

The last step is the damaging one, because Chainlit serves its own JavaScript
bundle that way. The browser gets a 500 for the bundle, React never mounts, and
the page renders as an empty document with only the stylesheet showing.

The standard library still carries the pure-Python ``current_task``, which reads
the same registry the Python task writes to, so pointing the public name at it
makes detection agree with reality again. anyio binds the function directly at
import, so its backend module is corrected too when it has already been loaded.

Import this module before anything else in ``app.py``.
"""

from __future__ import annotations

import asyncio
import asyncio.tasks
import sys


def _patch_needed() -> bool:
    """True when nest_asyncio has left ``current_task`` unable to see tasks."""
    if "nest_asyncio" not in sys.modules:
        return False
    python_task = getattr(asyncio.tasks, "_PyTask", None)
    python_current = getattr(asyncio.tasks, "_py_current_task", None)
    if python_task is None or python_current is None:
        return False
    # The swap is what breaks it, and there is nothing to do if the public name
    # already points at the implementation that matches the task class in use.
    return asyncio.Task is python_task and asyncio.current_task is not python_current


def repair_current_task() -> bool:
    """Point ``current_task`` at the implementation that matches the task class.

    Returns True if anything was changed. Running the app or the tests outside
    Chainlit's CLI leaves this a no-op, because nest_asyncio is not involved.
    """
    if not _patch_needed():
        return False

    python_current = asyncio.tasks._py_current_task
    asyncio.current_task = python_current
    asyncio.tasks.current_task = python_current

    # anyio does `from asyncio import current_task`, so a module that imported
    # before this ran still holds the broken reference.
    backend = sys.modules.get("anyio._backends._asyncio")
    if backend is not None:
        backend.current_task = python_current

    return True


REPAIRED = repair_current_task()
