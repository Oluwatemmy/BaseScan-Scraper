from fastapi import APIRouter, Depends, Path

from basescan_scraper.api.deps import get_transaction_service
from basescan_scraper.api.validators import validate_txhash
from basescan_scraper.models.transaction import (
    EventLog,
    TransactionDetail,
    TransactionLogs,
)
from basescan_scraper.services.transaction_service import TransactionService

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])

_RESPONSES = {
    404: {"description": "Transaction not found"},
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
_HASH_PATH = Path(..., examples=["0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"])


@router.get("/{tx_hash}", response_model=TransactionDetail, summary="Get transaction detail",
            operation_id="getTransaction", responses=_RESPONSES)
async def get_transaction(tx_hash: str = _HASH_PATH,
                          service: TransactionService = Depends(get_transaction_service)) -> TransactionDetail:
    """Core details + ERC-20 token transfers + input data for a transaction."""
    return await service.get_transaction(validate_txhash(tx_hash))


@router.get("/{tx_hash}/logs", response_model=TransactionLogs,
            summary="Get transaction event logs",
            operation_id="getTransactionLogs", responses=_RESPONSES)
async def get_logs(tx_hash: str = _HASH_PATH,
                   service: TransactionService = Depends(get_transaction_service)) -> TransactionLogs:
    """Event logs emitted by the transaction."""
    logs: list[EventLog] = await service.get_logs(validate_txhash(tx_hash))
    return TransactionLogs(data=logs)
