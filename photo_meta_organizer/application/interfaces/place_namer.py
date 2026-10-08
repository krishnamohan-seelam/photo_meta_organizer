"""Port for turning coordinates into a human place name (Map view cluster labels)."""

from typing import Literal, Protocol, runtime_checkable

PlaceScope = Literal["city", "country"]


@runtime_checkable
class PlaceNamer(Protocol):
    def name(self, latitude: float, longitude: float, scope: PlaceScope = "city") -> str | None:
        """The nearest place to a point, or ``None`` if nothing is close enough.

        ``scope="city"`` gives ``"Tokyo, Japan"``; ``scope="country"`` gives ``"Japan"`` and
        tolerates a larger distance, for clusters that span a whole region.
        """
        ...
