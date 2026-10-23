"""Trade contracts, in-memory parsers, synthetic fixtures and batch persistence."""

from marketlab.trades.fixtures import synthetic_trades
from marketlab.trades.parsers import TradeParseError, parse_trades_csv, parse_trades_json
from marketlab.trades.persistence import (
    DuplicateTradeError,
    get_trade,
    import_trades_csv,
    import_trades_json,
    list_trades,
)
from marketlab.trades.schemas import Trade

__all__ = [
    "DuplicateTradeError",
    "Trade",
    "TradeParseError",
    "get_trade",
    "import_trades_csv",
    "import_trades_json",
    "list_trades",
    "parse_trades_csv",
    "parse_trades_json",
    "synthetic_trades",
]
