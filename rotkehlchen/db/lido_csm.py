import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pysqlcipher3 import dbapi2 as sqlcipher

from rotkehlchen.errors.misc import InputError
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import ChecksumEvmAddress
from rotkehlchen.utils.misc import ts_now

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.db.drivers.gevent import DBCursor

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


@dataclass(frozen=True, slots=True)
class LidoCsmNodeOperator:
    """Represents a Lido CSM node operator entry owned by the user."""

    address: ChecksumEvmAddress
    node_operator_id: int
    metrics: dict[str, Any] | None = None


def _serialize_metrics_row(row: tuple[Any, ...]) -> dict[str, Any] | None:
    (
        operator_type_id,
        operator_type_label,
        bond_current,
        bond_required,
        bond_claimable,
        total_deposited_keys,
        rewards_pending,
    ) = row

    if all(value is None for value in row):
        return None

    metrics: dict[str, Any] = {}
    metrics['operator_type'] = (
        None if operator_type_id is None and operator_type_label is None else {
            'id': operator_type_id,
            'label': operator_type_label,
        }
    )
    metrics['bond'] = (
        None if bond_current is None and bond_required is None and bond_claimable is None else {
            'current': bond_current,
            'required': bond_required,
            'claimable': bond_claimable,
        }
    )
    metrics['keys'] = (
        None if total_deposited_keys is None else {
            'total_deposited': total_deposited_keys,
        }
    )
    metrics['rewards'] = (
        None if rewards_pending is None else {
            'pending': rewards_pending,
        }
    )

    return metrics


def _dict_get(data: Any, key: str) -> Any:
    return data.get(key) if isinstance(data, dict) else None


def _parse_metrics_payload(metrics: dict[str, Any]) -> tuple[Any, ...]:
    operator_type = _dict_get(metrics, 'operator_type')
    bond = _dict_get(metrics, 'bond')
    keys = _dict_get(metrics, 'keys')
    rewards = _dict_get(metrics, 'rewards')

    operator_type_id = _dict_get(operator_type, 'id')
    operator_type_label = _dict_get(operator_type, 'label')
    bond_current = _dict_get(bond, 'current')
    bond_required = _dict_get(bond, 'required')
    bond_claimable = _dict_get(bond, 'claimable')
    total_deposited_keys = _dict_get(keys, 'total_deposited')
    rewards_pending = _dict_get(rewards, 'pending')

    return (
        operator_type_id,
        operator_type_label,
        bond_current,
        bond_required,
        bond_claimable,
        total_deposited_keys,
        rewards_pending,
    )


class DBLidoCsm:
    """Persistence helper for Lido CSM node operator metadata."""

    def __init__(self, database: 'DBHandler') -> None:
        self.db = database

    @staticmethod
    def _serialize_entry(row: tuple[Any, ...]) -> LidoCsmNodeOperator:
        address, node_operator_id, *metrics_parts = row
        metrics = _serialize_metrics_row(tuple(metrics_parts))
        return LidoCsmNodeOperator(
            address=ChecksumEvmAddress(address),
            node_operator_id=int(node_operator_id),
            metrics=metrics,
        )

    def _fetch_entries(self, cursor: 'DBCursor') -> tuple[LidoCsmNodeOperator, ...]:
        result = cursor.execute(
            """
            SELECT
                o.address,
                o.node_operator_id,
                m.operator_type_id,
                m.operator_type_label,
                m.bond_current,
                m.bond_required,
                m.bond_claimable,
                m.total_deposited_keys,
                m.rewards_pending
            FROM lido_csm_node_operators AS o
            LEFT JOIN lido_csm_node_operator_metrics AS m
                ON o.node_operator_id = m.node_operator_id
            ORDER BY o.node_operator_id
            """,
        )
        return tuple(self._serialize_entry(row) for row in result.fetchall())

    def get_node_operators(self) -> tuple[LidoCsmNodeOperator, ...]:
        with self.db.conn.read_ctx() as cursor:
            return self._fetch_entries(cursor)

    def add_node_operator(
            self,
            address: ChecksumEvmAddress,
            node_operator_id: int,
    ) -> None:
        if node_operator_id < 0:
            raise InputError('Node operator id must be >= 0')

        with self.db.user_write() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO lido_csm_node_operators(node_operator_id, address)
                    VALUES(?, ?)
                    """,
                    (node_operator_id, address),
                )
            except sqlcipher.IntegrityError as exc:  # pylint: disable=no-member
                raise InputError(f'Node operator id {node_operator_id} is already tracked') from exc

    def set_metrics(self, node_operator_id: int, metrics: dict[str, Any]) -> None:
        columns = _parse_metrics_payload(metrics)
        with self.db.user_write() as cursor:
            existing = cursor.execute(
                'SELECT 1 FROM lido_csm_node_operators WHERE node_operator_id=?',
                (node_operator_id,),
            ).fetchone()
            if existing is None:
                raise InputError(f'Node operator id {node_operator_id} is not tracked')

            cursor.execute(
                """
                INSERT INTO lido_csm_node_operator_metrics(
                    node_operator_id,
                    operator_type_id,
                    operator_type_label,
                    bond_current,
                    bond_required,
                    bond_claimable,
                    total_deposited_keys,
                    rewards_pending,
                    updated_ts
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_operator_id) DO UPDATE SET
                    operator_type_id=excluded.operator_type_id,
                    operator_type_label=excluded.operator_type_label,
                    bond_current=excluded.bond_current,
                    bond_required=excluded.bond_required,
                    bond_claimable=excluded.bond_claimable,
                    total_deposited_keys=excluded.total_deposited_keys,
                    rewards_pending=excluded.rewards_pending,
                    updated_ts=excluded.updated_ts
                """,
                (node_operator_id, *columns, ts_now()),
            )

    def delete_metrics(self, node_operator_id: int) -> None:
        with self.db.user_write() as cursor:
            cursor.execute(
                'DELETE FROM lido_csm_node_operator_metrics WHERE node_operator_id=?',
                (node_operator_id,),
            )

    def remove_node_operator(
            self,
            address: ChecksumEvmAddress,
            node_operator_id: int,
    ) -> None:
        with self.db.user_write() as cursor:
            row = cursor.execute(
                'SELECT address FROM lido_csm_node_operators WHERE node_operator_id=?',
                (node_operator_id,),
            ).fetchone()
            if row is None:
                raise InputError(
                    f'Node operator with id {node_operator_id} for {address} is not tracked',
                )

            stored_address = ChecksumEvmAddress(row[0])
            if stored_address != address:
                raise InputError(
                    f'Node operator id {node_operator_id} is tracked for {stored_address}, not {address}',
                )

            cursor.execute(
                'DELETE FROM lido_csm_node_operators WHERE node_operator_id=?',
                (node_operator_id,),
            )
