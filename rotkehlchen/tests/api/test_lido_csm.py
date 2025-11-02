from types import SimpleNamespace

import requests

from rotkehlchen.db.lido_csm import DBLidoCsm
from rotkehlchen.tests.utils.api import api_url_for, assert_proper_sync_response_with_result
from rotkehlchen.tests.utils.factories import make_evm_address


def test_set_and_delete_metrics(database) -> None:
    db = DBLidoCsm(database)
    address = make_evm_address()
    db.add_node_operator(address=address, node_operator_id=1)

    metrics_payload = {
        'operator_type': {'id': 1, 'label': 'Permissionless'},
        'bond': {'current': '1', 'required': '2', 'claimable': '0.5'},
        'keys': {'total_deposited': 42},
        'rewards': {'pending': '0.3'},
    }

    db.set_metrics(1, metrics_payload)
    entries = db.get_node_operators()
    assert entries == (DBLidoCsm._deserialize(DBLidoCsm._serialize(entries[0])),)  # sanity
    assert entries[0].metrics == metrics_payload

    db.delete_metrics(1)
    entries = db.get_node_operators()
    assert entries[0].metrics is None


def test_refresh_metrics_endpoint_persists(rotkehlchen_api_server, monkeypatch) -> None:
    rotki = rotkehlchen_api_server.rest_api.rotkehlchen
    db = DBLidoCsm(rotki.data.db)
    address = make_evm_address()
    db.add_node_operator(address=address, node_operator_id=7)

    # Ensure the test client is treated as a logged in user
    rotki.user_is_logged_in = True
    rotki.data.username = 'testuser'

    metrics_payload = {
        'operator_type': {'id': 2, 'label': 'Permissioned'},
        'bond': {'current': '1.5'},
        'keys': {'total_deposited': 100},
        'rewards': {'pending': '0.0'},
    }

    # Monkeypatch the metrics fetcher to return our payload
    def fake_get_operator_stats(self, node_operator_id: int):
        return SimpleNamespace(serialize=lambda: metrics_payload)

    import rotkehlchen.chain.ethereum.modules.lido_csm.metrics as metrics_mod
    monkeypatch.setattr(metrics_mod.LidoCsmMetricsFetcher, 'get_operator_stats', fake_get_operator_stats)

    response = requests.post(api_url_for(rotkehlchen_api_server, 'lidocsmmetricsresource'))
    result = assert_proper_sync_response_with_result(response)

    # Verify DB persisted metrics
    entries = db.get_node_operators()
    assert len(entries) == 1
    assert entries[0].node_operator_id == 7
    assert entries[0].metrics == metrics_payload
