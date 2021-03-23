import logging

from brownie import chain, web3
from brownie.network.event import EventDict, _decode_logs
from joblib import Parallel, delayed
from web3.middleware.filter import block_ranges

from yearn.cache import memory
from yearn.middleware import BATCH_SIZE

logger = logging.getLogger(__name__)


@memory.cache()
def contract_creation_block(address) -> int:
    """
    Use binary search to determine the block when a contract was created.
    NOTE Requires access to archive state. A recommended option is Turbo Geth.

    TODO Add fallback to BigQuery
    """
    logger.info("contract creation block %s", address)
    height = chain.height
    lo, hi = 0, height
    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if web3.eth.getCode(address, block_identifier=mid):
            hi = mid
        else:
            lo = mid
    return hi if hi != height else None


def decode_logs(logs) -> EventDict:
    """
    Decode logs to events and enrich them with additional info.
    """
    decoded = _decode_logs(logs)
    for i, log in enumerate(logs):
        setattr(decoded[i], "block_number", log["blockNumber"])
        setattr(decoded[i], "transaction_hash", log["transactionHash"])
        setattr(decoded[i], "log_index", log["logIndex"])
    return decoded


def create_filter(address, topics=None):
    """
    Create a log filter for one or more contracts.
    Set fromBlock as the earliest creation block.
    """
    if isinstance(address, list):
        start_block = min(map(contract_creation_block, address))
    else:
        start_block = contract_creation_block(address)

    return web3.eth.filter({"address": address, "fromBlock": start_block, "topics": topics})


def get_logs_asap(address, topics, from_block, to_block):
    logs = []
    batches = Parallel(8, "threading", verbose=10)(
        delayed(web3.eth.getLogs)({"address": address, "topics": topics, "fromBlock": start, "toBlock": end})
        for start, end in block_ranges(from_block, to_block, BATCH_SIZE)
    )
    for batch in batches:
        logs.extend(batch)

    return logs
