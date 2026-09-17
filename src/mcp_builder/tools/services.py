"""Per-server dependencies shared by registered tools."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_builder.search.store import Store

@dataclass
class Services:
    """Hold one server's initialized corpus; tests may inject a deterministic Store."""
    store: "Store | None" = None

    def documents(self) -> "Store":
        """Return the loaded corpus or fail explicitly before initialization."""
        if self.store is None:
            raise RuntimeError("Documentation not initialized")
        return self.store
