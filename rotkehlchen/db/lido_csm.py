import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from eth_utils import to_checksum_address

from rotkehlchen.errors.misc import InputError
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import ChecksumEvmAddress

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.db.drivers.gevent import DBCursor

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

NODE_OPERATOR_KEY: Final = 'lido_csm_node_operator'


@dataclass(frozen=True, slots=True)
class LidoCsmNodeOperator:
    """Represents a Lido CSM node operator entry owned by the user."""

    address: ChecksumEvmAddress
    node_operator_id: int
    metrics: dict | None = None


class DBLidoCsm:
    """Persistence helper for Lido CSM node operator metadata."""

    def __init__(self, database: 'DBHandler') -> None:
        self.db = database

    @staticmethod
    def _serialize(entry: LidoCsmNodeOperator) -> str:
        return json.dumps(
            {
                'address': entry.address,
                'node_operator_id': entry.node_operator_id,
                **({'metrics': entry.metrics} if entry.metrics is not None else {}),
            },
            separators=(',', ':'),
            sort_keys=True,
        )

    @staticmethod
    def _deserialize(value: str) -> LidoCsmNodeOperator | None:
        try:
            raw = json.loads(value)
            address = to_checksum_address(raw['address'])
            node_operator_id = int(raw['node_operator_id'])
            metrics = raw.get('metrics')
            if node_operator_id < 0:
                raise ValueError('Invalid node operator id')
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            log.error('Failed to deserialize Lido CSM node-operator entry %s due to %s', value, exc)
            return None

        return LidoCsmNodeOperator(address=address, node_operator_id=node_operator_id, metrics=metrics)

    def _fetch_entries(self, cursor: 'DBCursor') -> tuple[LidoCsmNodeOperator, ...]:
        result = cursor.execute(
            'SELECT value FROM multisettings WHERE name=?',
            (NODE_OPERATOR_KEY,),
        )
        entries: list[LidoCsmNodeOperator] = []
        for (value,) in result.fetchall():
            if (entry := self._deserialize(value)) is not None:
                entries.append(entry)

        return tuple(entries)

    def get_node_operators(self) -> tuple[LidoCsmNodeOperator, ...]:
        with self.db.conn.read_ctx() as cursor:
            return self._fetch_entries(cursor)

    def _ensure_unique_id(
            self,
            cursor: 'DBCursor',
            node_operator_id: int,
    ) -> None:
        existing = cursor.execute(
            """
            SELECT 1 FROM multisettings
            WHERE name=? AND json_extract(value, '$.node_operator_id')=?
            """,
            (NODE_OPERATOR_KEY, node_operator_id),
        ).fetchone()
        if existing is not None:
            raise InputError(f'Node operator id {node_operator_id} is already tracked')

    def add_node_operator(
            self,
            address: ChecksumEvmAddress,
            node_operator_id: int,
    ) -> None:
        if node_operator_id < 0:
            raise InputError('Node operator id must be >= 0')

        entry = LidoCsmNodeOperator(address=address, node_operator_id=node_operator_id)
        serialized = self._serialize(entry)
        with self.db.user_write() as cursor:
            self._ensure_unique_id(cursor, node_operator_id)
            cursor.execute(
                'INSERT INTO multisettings(name, value) VALUES(?, ?)',
                (NODE_OPERATOR_KEY, serialized),
            )

    def set_metrics(self, node_operator_id: int, metrics: dict) -> None:
        """Set or update the metrics field for the given tracked node operator.

        This updates the multisettings row that matches the node_operator_id.
        """
        with self.db.user_write() as cursor:
            # fetch the current value
            row = cursor.execute(
                'SELECT value FROM multisettings WHERE name=? AND json_extract(value, "$.node_operator_id")=?;',
                (NODE_OPERATOR_KEY, node_operator_id),
            ).fetchone()
            if row is None:
                raise InputError(f'Node operator id {node_operator_id} is not tracked')
            current = row[0]
            entry = self._deserialize(current)
            if entry is None:
                raise InputError(f'Failed to deserialize stored node operator {node_operator_id}')
            # create a new serialized value including metrics
            new_entry = LidoCsmNodeOperator(address=entry.address, node_operator_id=entry.node_operator_id, metrics=metrics)
            serialized = self._serialize(new_entry)
            cursor.execute(
                'UPDATE multisettings SET value=? WHERE name=? AND json_extract(value, "$.node_operator_id")=?;',
                (serialized, NODE_OPERATOR_KEY, node_operator_id),
            )

    def delete_metrics(self, node_operator_id: int) -> None:
        """Remove the metrics key from the stored entry for the given node operator id."""
        with self.db.user_write() as cursor:
            cursor.execute(
                "UPDATE multisettings SET value=json_remove(value, '$.metrics') WHERE name=? AND json_extract(value, '$.node_operator_id')=?;",
                (NODE_OPERATOR_KEY, node_operator_id),
            )

    def remove_node_operator(
            self,
            address: ChecksumEvmAddress,
            node_operator_id: int,
    ) -> None:
        with self.db.user_write() as cursor:
            cursor.execute(
                'DELETE FROM multisettings WHERE name=? AND json_extract(value, "$.node_operator_id")=?',
                (NODE_OPERATOR_KEY, node_operator_id),
            )
            if cursor.rowcount != 1:
                raise InputError(
                    f'Node operator with id {node_operator_id} for {address} is not tracked',
                )

    def upsert_entries(self, entries: Sequence[LidoCsmNodeOperator]) -> None:
        """Utility for tests to replace all stored entries."""
        with self.db.user_write() as cursor:
            cursor.execute('DELETE FROM multisettings WHERE name=?', (NODE_OPERATOR_KEY,))
            for entry in entries:
                cursor.execute(
                    'INSERT INTO multisettings(name, value) VALUES(?, ?)',
                    (NODE_OPERATOR_KEY, self._serialize(entry)),
                )
