"""No-op sink implementation."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.sink import Sink


class NullSink(Sink):
    """
    No-op sink that discards all data.

    Used when a sink is structurally required but the output is disabled
    (e.g. rejection log disabled via --no-rejection-log).
    """

    async def open(self) -> None:
        pass

    async def push(self, item) -> None:
        pass

    async def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return "NullSink()"
