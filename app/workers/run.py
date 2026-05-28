from __future__ import annotations

import asyncio

from app.workers.consumer import consumer


def main() -> None:
    asyncio.run(consumer.run_forever())


if __name__ == "__main__":  # pragma: no cover
    main()
