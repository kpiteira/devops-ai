"""One module per provider; the resolver discovers them, never names them.

A module in this package is a provider when it exports `SCHEME`, `handles` and
`resolve`. Adding a backend means adding a module here and nothing else.
Modules whose name starts with `_` are shared helpers, not providers.
"""

from __future__ import annotations
