import pytest
from eth_utils import to_checksum_address

from rotkehlchen.db.lido_csm import DBLidoCsm, LidoCsmNodeOperator
from rotkehlchen.errors.misc import InputError


def test_add_and_list_node_operators(database) -> None:
    db = DBLidoCsm(database)
    address = to_checksum_address('0xBEEF00000000000000000000000000000000BEEF')
    db.add_node_operator(address=address, node_operator_id=1)

    assert db.get_node_operators() == (
        LidoCsmNodeOperator(address=address, node_operator_id=1, metrics=None),
    )


def test_duplicate_node_operator_id(database) -> None:
    db = DBLidoCsm(database)
    address = to_checksum_address('0x1111000000000000000000000000000000001111')
    db.add_node_operator(address=address, node_operator_id=7)

    with pytest.raises(InputError):
        db.add_node_operator(
            address=to_checksum_address('0x2222000000000000000000000000000000002222'),
            node_operator_id=7,
        )


def test_set_and_delete_metrics(database) -> None:
    db = DBLidoCsm(database)
    address = to_checksum_address('0x1234000000000000000000000000000000005678')
    db.add_node_operator(address=address, node_operator_id=3)

    metrics_payload = {
        'operator_type': {'id': 1, 'label': 'Permissionless'},
        'bond': {'current': '1.0', 'required': '2.0', 'claimable': '0.5'},
        'keys': {'total_deposited': 42},
        'rewards': {'pending': '0.3'},
    }
    db.set_metrics(node_operator_id=3, metrics=metrics_payload)

    entries = db.get_node_operators()
    assert entries == (
        LidoCsmNodeOperator(
            address=address,
            node_operator_id=3,
            metrics=metrics_payload,
        ),
    )

    db.delete_metrics(node_operator_id=3)
    entries = db.get_node_operators()
    assert entries == (
        LidoCsmNodeOperator(
            address=address,
            node_operator_id=3,
            metrics=None,
        ),
    )


def test_remove_node_operator(database) -> None:
    db = DBLidoCsm(database)
    address = to_checksum_address('0x999900000000000000000000000000000000AAAA')
    db.add_node_operator(address=address, node_operator_id=5)

    db.remove_node_operator(address=address, node_operator_id=5)
    assert db.get_node_operators() == ()

    with pytest.raises(InputError):
        db.remove_node_operator(address=address, node_operator_id=5)


def test_remove_node_operator_wrong_address(database) -> None:
    db = DBLidoCsm(database)
    tracked_address = to_checksum_address('0xABCD00000000000000000000000000000000ABCD')
    db.add_node_operator(address=tracked_address, node_operator_id=9)

    with pytest.raises(InputError):
        db.remove_node_operator(
            address=to_checksum_address('0xDEAD00000000000000000000000000000000BEEF'),
            node_operator_id=9,
        )
