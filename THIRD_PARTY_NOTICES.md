# Dependencies

Telegram Local's wrapper and skill are MIT licensed. The MCP tools are supplied
by [chigwell/telegram-mcp](https://github.com/chigwell/telegram-mcp), Apache-2.0,
pinned at commit `e55d9c7a66a8eb0855debb268a4ed5b63749af2d` (version 2.0.1).
That code is installed as a dependency; this repository does not claim its
tools as original work. Its license remains in the installed distribution and
upstream repository. Runtime dependencies retain their respective licenses.

The PyPI name `telegram-mcp` belongs to another project according to upstream's
installation guard. Use the pinned Git dependency here; do not substitute a
bare `pip install telegram-mcp`.

This project is independent of Telegram and OpenAI and has no official
endorsement from either company.
