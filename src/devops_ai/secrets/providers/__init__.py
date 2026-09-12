"""One module per provider; the resolver discovers them, never names them.

Every module here whose name does not start with `_` is loaded as a provider and
must export `SCHEME`, `handles` and `resolve`; `_`-prefixed modules are shared
helpers the resolver skips. Adding a backend means adding a module here and
nothing else — the architecture test pins exactly that.
"""

from __future__ import annotations
