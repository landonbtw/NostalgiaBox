"""Randomized, no-boring-repeats playlist ordering.

Old TV was appointment viewing on a schedule; this box instead plays each
channel on an endless shuffle. A naive "pick a random file every time" feels
wrong: it will happily play the same episode twice in a row and can go a long
time without touching some episodes. A *shuffle bag* fixes both problems.

The bag holds one copy of every episode. It hands them out in a random order
until the bag is empty, then refills and reshuffles - guaranteeing every
episode plays once before any repeats (just like dragging a season into a music
player and hitting "shuffle"). When it refills, it also makes sure the first
episode of the new shuffle is not the same as the last one played, so you never
see the same episode back-to-back across a cycle boundary.
"""

from __future__ import annotations

import random
from typing import Generic, List, Optional, Sequence, TypeVar

T = TypeVar("T")


class ShuffleBag(Generic[T]):
    """Yields items in a random order, once each, then reshuffles."""

    def __init__(self, items: Sequence[T], rng: Optional[random.Random] = None) -> None:
        self._items: List[T] = list(items)
        self._rng = rng or random.Random()
        self._queue: List[T] = []
        self._last: Optional[T] = None
        self._refill()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        return not self._items

    def _refill(self) -> None:
        self._queue = list(self._items)
        self._rng.shuffle(self._queue)
        # Avoid an immediate repeat across the cycle boundary: if the first
        # item of the fresh shuffle is what we just played, and there is more
        # than one item, swap it deeper into the queue.
        if (
            len(self._queue) > 1
            and self._last is not None
            and self._queue[-1] == self._last
        ):
            # _last would be the *next* item popped (we pop from the end), so
            # move it to the front of the play order instead.
            self._queue.insert(0, self._queue.pop())

    def next(self) -> T:
        """Return the next item, refilling the bag if it has been exhausted."""
        if not self._items:
            raise IndexError("cannot draw from an empty ShuffleBag")
        if not self._queue:
            self._refill()
        item = self._queue.pop()
        self._last = item
        return item

    def peek_remaining(self) -> int:
        """How many items are left before the next reshuffle (for debugging)."""
        return len(self._queue)


__all__ = ["ShuffleBag"]
