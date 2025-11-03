from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from eth_utils import to_checksum_address

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.chain.ethereum.modules.lido_csm.balances import LidoCsmBalances
from rotkehlchen.chain.ethereum.modules.lido_csm.metrics import LidoCsmMetricsFetcher, LidoCsmNodeOperatorStats
from rotkehlchen.chain.ethereum.modules.lido_csm.constants import CPT_LIDO_CSM
from rotkehlchen.constants.assets import A_STETH
from rotkehlchen.db.lido_csm import LidoCsmNodeOperator
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.fval import FVal
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.types import ChainID


def _make_evm_inquirer():
    return SimpleNamespace(
        database=MagicMock(),
        chain_id=ChainID.ETHEREUM,
    )


def test_lido_csm_balances_accumulates():
    entry = LidoCsmNodeOperator(
        address=to_checksum_address('0xABCD00000000000000000000000000000000ABCD'),
        node_operator_id=9,
    )
    with patch(
        'rotkehlchen.db.lido_csm.DBLidoCsm.get_node_operators',
        return_value=(entry,),
    ), patch.object(
        LidoCsmBalances,
        '_get_bond_shares',
        return_value=1_000_000_000_000_000_000,
    ), patch.object(
        LidoCsmBalances,
        '_convert_shares_to_steth',
        return_value=FVal('1.5'),
    ), patch.object(
        Inquirer,
        'find_usd_price',
        return_value=FVal('2000'),
    ), patch.object(
        LidoCsmMetricsFetcher,
        'get_operator_stats',
        return_value=LidoCsmNodeOperatorStats(
            operator_type_id=0,
            operator_type_label='Unknown',
            current_bond=FVal(0),
            required_bond=FVal(0),
            claimable_bond=FVal(0),
            total_deposited_keys=0,
            rewards_steth=FVal(0),
        ),
    ):
        balances = LidoCsmBalances(
            evm_inquirer=_make_evm_inquirer(),
            tx_decoder=MagicMock(),
        )
        result = balances.query_balances()

    steth_token = A_STETH.resolve_to_evm_token()
    assert result[entry.address].assets[steth_token][CPT_LIDO_CSM] == Balance(
        amount=FVal('1.5'),
        usd_value=FVal('3000'),
    )


def test_lido_csm_balances_skips_on_error():
    entry = LidoCsmNodeOperator(
        address=to_checksum_address('0x1234500000000000000000000000000000006789'),
        node_operator_id=5,
    )
    def _raise_remote_error(*_args, **_kwargs):
        raise RemoteError('boom')

    with patch(
        'rotkehlchen.db.lido_csm.DBLidoCsm.get_node_operators',
        return_value=(entry,),
    ), patch.object(
        LidoCsmBalances,
        '_get_bond_shares',
        side_effect=_raise_remote_error,
    ), patch.object(
        Inquirer,
        'find_usd_price',
        return_value=FVal('2000'),
    ), patch.object(
        LidoCsmMetricsFetcher,
        'get_operator_stats',
        return_value=LidoCsmNodeOperatorStats(
            operator_type_id=0,
            operator_type_label='Unknown',
            current_bond=FVal(0),
            required_bond=FVal(0),
            claimable_bond=FVal(0),
            total_deposited_keys=0,
            rewards_steth=FVal(0),
        ),
    ):
        balances = LidoCsmBalances(
            evm_inquirer=_make_evm_inquirer(),
            tx_decoder=MagicMock(),
        )
        result = balances.query_balances()
    assert len(result) == 0
