from types import SimpleNamespace
from unittest.mock import patch

import requests

from rotkehlchen.db.lido_csm import DBLidoCsm
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_sync_response_with_result
from rotkehlchen.tests.utils.factories import make_evm_address


def _login(rotkehlchen_api_server):
    rotki = rotkehlchen_api_server.rest_api.rotkehlchen
    rotki.user_is_logged_in = True
    rotki.data.username = 'testuser'
    return rotki


def _strip_none_values(data):
    if isinstance(data, dict):
        return {key: _strip_none_values(value) for key, value in data.items() if value is not None}
    return data


def test_get_lido_csm_node_operators(rotkehlchen_api_server) -> None:
    rotki = _login(rotkehlchen_api_server)
    db = DBLidoCsm(rotki.data.db)

    address = make_evm_address()
    db.add_node_operator(address=address, node_operator_id=5)
    db.set_metrics(5, {'operator_type': {'id': 1, 'label': 'Permissionless'}})

    response = requests.get(api_url_for(rotkehlchen_api_server, 'lidocsmnodeoperatorresource'))
    result = assert_proper_sync_response_with_result(response)

    assert result == [{
        'address': address,
        'node_operator_id': 5,
        'metrics': {
            'operator_type': {'id': 1, 'label': 'Permissionless'},
            'bond': None,
            'keys': None,
            'rewards': None,
        },
    }]


def test_add_lido_csm_node_operator(rotkehlchen_api_server) -> None:
    rotki = _login(rotkehlchen_api_server)
    db = DBLidoCsm(rotki.data.db)

    address = make_evm_address()
    metrics_payload = {
        'operator_type': {'id': 2, 'label': 'ICS'},
        'bond': {'current': '1', 'required': '1', 'claimable': '0'},
        'keys': {'total_deposited': 42},
        'rewards': {'pending': '0.1'},
    }

    with patch(
        'rotkehlchen.chain.ethereum.modules.lido_csm.metrics.LidoCsmMetricsFetcher.get_operator_stats',
        return_value=SimpleNamespace(serialize=lambda: metrics_payload),
    ):
        response = requests.put(
            api_url_for(rotkehlchen_api_server, 'lidocsmnodeoperatorresource'),
            json={
                'address': address,
                'node_operator_id': 10,
            },
        )

    result = assert_proper_sync_response_with_result(response)
    assert len(result) == 1
    assert result[0]['node_operator_id'] == 10

    entries = db.get_node_operators()
    assert len(entries) == 1
    assert entries[0].node_operator_id == 10
    assert entries[0].metrics == metrics_payload


def test_delete_lido_csm_node_operator(rotkehlchen_api_server) -> None:
    rotki = _login(rotkehlchen_api_server)
    db = DBLidoCsm(rotki.data.db)

    address = make_evm_address()
    db.add_node_operator(address=address, node_operator_id=3)

    response = requests.delete(
        api_url_for(rotkehlchen_api_server, 'lidocsmnodeoperatorresource'),
        json={
            'address': address,
            'node_operator_id': 3,
        },
    )
    result = assert_proper_sync_response_with_result(response)
    assert result == []
    assert db.get_node_operators() == ()


def test_refresh_metrics_endpoint_persists(rotkehlchen_api_server) -> None:
    rotki = _login(rotkehlchen_api_server)
    db = DBLidoCsm(rotki.data.db)
    address = make_evm_address()
    db.add_node_operator(address=address, node_operator_id=7)

    metrics_payload = {
        'operator_type': {'id': 2, 'label': 'Permissioned'},
        'bond': {'current': '1.5'},
        'keys': {'total_deposited': 100},
        'rewards': {'pending': '0.0'},
    }

    with patch(
        'rotkehlchen.chain.ethereum.modules.lido_csm.metrics.LidoCsmMetricsFetcher.get_operator_stats',
        return_value=SimpleNamespace(serialize=lambda: metrics_payload),
    ):
        response = requests.post(api_url_for(rotkehlchen_api_server, 'lidocsmmetricsresource'))

    result = assert_proper_sync_response_with_result(response)
    assert len(result) == 1
    assert result[0]['node_operator_id'] == 7

    # Verify DB persisted metrics
    entries = db.get_node_operators()
    assert len(entries) == 1
    assert entries[0].node_operator_id == 7
    assert _strip_none_values(entries[0].metrics) == metrics_payload
