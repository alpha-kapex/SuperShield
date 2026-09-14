"""State and temporary-document adapters.

The in-memory adapters power local replay and tests. AWS adapters import boto3
only when selected, so the same package remains usable without AWS extras.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol

from supershield.models import CaseRecord, EvidenceDocument, RunEvent, RunRecord


class RecordNotFound(KeyError):
    pass


class RecordConflict(RuntimeError):
    pass


class StateStore(Protocol):
    name: str

    def put_case(self, case: CaseRecord, *, create_only: bool = False) -> None: ...

    def get_case(self, case_id: str) -> CaseRecord: ...

    def delete_case(self, case_id: str) -> bool: ...

    def put_run(self, run: RunRecord, *, create_only: bool = False) -> None: ...

    def get_run(self, run_id: str) -> RunRecord: ...

    def list_runs(self, case_id: str) -> list[RunRecord]: ...

    def append_event(self, event: RunEvent) -> None: ...

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]: ...


class DocumentStore(Protocol):
    name: str

    def put(self, key: str, content: bytes, *, content_type: str = "text/plain") -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class InMemoryStateStore:
    name = "memory"

    def __init__(self) -> None:
        self._cases: dict[str, CaseRecord] = {}
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[RunEvent]] = defaultdict(list)
        self._lock = threading.RLock()

    def put_case(self, case: CaseRecord, *, create_only: bool = False) -> None:
        with self._lock:
            if create_only and case.case_id in self._cases:
                raise RecordConflict(f"Case already exists: {case.case_id}")
            self._cases[case.case_id] = case.model_copy(deep=True)

    def get_case(self, case_id: str) -> CaseRecord:
        with self._lock:
            try:
                case = self._cases[case_id]
            except KeyError as exc:
                raise RecordNotFound(case_id) from exc
            if _expired(case):
                self.delete_case(case_id)
                raise RecordNotFound(case_id)
            return case.model_copy(deep=True)

    def delete_case(self, case_id: str) -> bool:
        with self._lock:
            if self._cases.pop(case_id, None) is None:
                return False
            run_ids = [run_id for run_id, run in self._runs.items() if run.case_id == case_id]
            for run_id in run_ids:
                del self._runs[run_id]
                self._events.pop(run_id, None)
            return True

    def put_run(self, run: RunRecord, *, create_only: bool = False) -> None:
        with self._lock:
            self.get_case(run.case_id)
            if create_only and run.run_id in self._runs:
                raise RecordConflict(f"Run already exists: {run.run_id}")
            self._runs[run.run_id] = run.model_copy(deep=True)

    def get_run(self, run_id: str) -> RunRecord:
        with self._lock:
            try:
                run = self._runs[run_id]
            except KeyError as exc:
                raise RecordNotFound(run_id) from exc
            try:
                self.get_case(run.case_id)
            except RecordNotFound as exc:
                raise RecordNotFound(run_id) from exc
            return run.model_copy(deep=True)

    def list_runs(self, case_id: str) -> list[RunRecord]:
        with self._lock:
            self.get_case(case_id)
            return sorted(
                (
                    run.model_copy(deep=True)
                    for run in self._runs.values()
                    if run.case_id == case_id
                ),
                key=lambda run: (run.created_at, run.run_id),
            )

    def append_event(self, event: RunEvent) -> None:
        with self._lock:
            self.get_run(event.run_id)
            expected = len(self._events[event.run_id]) + 1
            if event.sequence != expected:
                raise RecordConflict(
                    f"Expected event sequence {expected}, received {event.sequence}"
                )
            self._events[event.run_id].append(event.model_copy(deep=True))

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]:
        with self._lock:
            self.get_run(run_id)
            return [
                event.model_copy(deep=True)
                for event in self._events[run_id]
                if event.sequence > after_sequence
            ]


def _expired(case: CaseRecord, *, now: datetime | None = None) -> bool:
    if case.expires_at is None:
        return False
    comparison = now or datetime.now(UTC)
    expiry = case.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return expiry <= comparison


class InMemoryDocumentStore:
    name = "memory"

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._lock = threading.RLock()

    def put(self, key: str, content: bytes, *, content_type: str = "text/plain") -> None:
        del content_type
        with self._lock:
            self._objects[key] = bytes(content)

    def get(self, key: str) -> bytes:
        with self._lock:
            try:
                return bytes(self._objects[key])
            except KeyError as exc:
                raise RecordNotFound(key) from exc

    def delete(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)


def _ddb_payload(model: CaseRecord | RunRecord | RunEvent) -> dict[str, Any]:
    # Decimal is required for DynamoDB; JSON mode also normalizes datetimes/enums.
    return json.loads(model.model_dump_json(by_alias=False), parse_float=Decimal)


class DynamoDBStateStore:
    """Single-table adapter using ``pk``/``sk`` and DynamoDB TTL."""

    name = "dynamodb"

    def __init__(self, table_name: str, *, region_name: str) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Install SuperShield with the 'aws' extra for DynamoDB") from exc
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def put_case(self, case: CaseRecord, *, create_only: bool = False) -> None:
        kwargs: dict[str, Any] = {
            "Item": {
                "pk": f"CASE#{case.case_id}",
                "sk": "META",
                "kind": "case",
                "case_id": case.case_id,
                "payload": _ddb_payload(case),
                **(
                    {"expires_at": int(case.expires_at.timestamp())}
                    if case.expires_at is not None
                    else {}
                ),
            }
        }
        if create_only:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk)"
        try:
            self._table.put_item(**kwargs)
        except Exception as exc:  # pragma: no cover - requires AWS
            if "ConditionalCheckFailed" in type(exc).__name__:
                raise RecordConflict(case.case_id) from exc
            raise

    def get_case(self, case_id: str) -> CaseRecord:
        response = self._table.get_item(Key={"pk": f"CASE#{case_id}", "sk": "META"})
        if "Item" not in response:
            raise RecordNotFound(case_id)
        case = CaseRecord.model_validate(response["Item"]["payload"])
        if _expired(case):
            self._delete_case_records(case_id)
            raise RecordNotFound(case_id)
        return case

    def delete_case(self, case_id: str) -> bool:
        response = self._table.get_item(Key={"pk": f"CASE#{case_id}", "sk": "META"})
        if "Item" not in response:
            return False
        self._delete_case_records(case_id)
        return True

    def _delete_case_records(self, case_id: str) -> None:
        self._table.delete_item(Key={"pk": f"CASE#{case_id}", "sk": "META"})
        # Runs are separately partitioned; a case_id attribute supports this bounded cleanup.
        from boto3.dynamodb.conditions import Attr

        scan_args: dict[str, Any] = {
            "FilterExpression": Attr("case_id").eq(case_id),
            "ProjectionExpression": "pk, sk",
        }
        while True:
            response = self._table.scan(**scan_args)
            with self._table.batch_writer() as writer:
                for item in response.get("Items", []):
                    if item["pk"] != f"CASE#{case_id}":
                        writer.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_args["ExclusiveStartKey"] = last_key

    def put_run(self, run: RunRecord, *, create_only: bool = False) -> None:
        self.get_case(run.case_id)
        kwargs: dict[str, Any] = {
            "Item": {
                "pk": f"RUN#{run.run_id}",
                "sk": "META",
                "kind": "run",
                "case_id": run.case_id,
                "run_id": run.run_id,
                "payload": _ddb_payload(run),
            }
        }
        if create_only:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk)"
        try:
            self._table.put_item(**kwargs)
        except Exception as exc:  # pragma: no cover - requires AWS
            if "ConditionalCheckFailed" in type(exc).__name__:
                raise RecordConflict(run.run_id) from exc
            raise

    def get_run(self, run_id: str) -> RunRecord:
        response = self._table.get_item(Key={"pk": f"RUN#{run_id}", "sk": "META"})
        if "Item" not in response:
            raise RecordNotFound(run_id)
        run = RunRecord.model_validate(response["Item"]["payload"])
        try:
            self.get_case(run.case_id)
        except RecordNotFound as exc:
            raise RecordNotFound(run_id) from exc
        return run

    def list_runs(self, case_id: str) -> list[RunRecord]:
        from boto3.dynamodb.conditions import Attr

        self.get_case(case_id)
        scan_args: dict[str, Any] = {
            "FilterExpression": Attr("case_id").eq(case_id) & Attr("kind").eq("run")
        }
        runs: list[RunRecord] = []
        while True:
            response = self._table.scan(**scan_args)
            runs.extend(
                RunRecord.model_validate(item["payload"])
                for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_args["ExclusiveStartKey"] = last_key
        return sorted(runs, key=lambda run: (run.created_at, run.run_id))

    def append_event(self, event: RunEvent) -> None:
        self.get_run(event.run_id)
        try:
            self._table.put_item(
                Item={
                    "pk": f"RUN#{event.run_id}",
                    "sk": f"EVENT#{event.sequence:08d}",
                    "kind": "event",
                    "run_id": event.run_id,
                    "payload": _ddb_payload(event),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except Exception as exc:  # pragma: no cover - requires AWS
            if "ConditionalCheckFailed" in type(exc).__name__:
                raise RecordConflict(event.event_id) from exc
            raise

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]:
        from boto3.dynamodb.conditions import Key

        self.get_run(run_id)
        response = self._table.query(
            KeyConditionExpression=Key("pk").eq(f"RUN#{run_id}")
            & Key("sk").begins_with("EVENT#")
        )
        return [
            event
            for item in response.get("Items", [])
            if (event := RunEvent.model_validate(item["payload"])).sequence > after_sequence
        ]


class S3DocumentStore:
    name = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        region_name: str,
        kms_key_id: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Install SuperShield with the 'aws' extra for S3") from exc
        self._client = boto3.client("s3", region_name=region_name)
        self._bucket = bucket
        self._kms_key_id = kms_key_id

    def put(self, key: str, content: bytes, *, content_type: str = "text/plain") -> None:
        encryption = (
            {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms_key_id}
            if self._kms_key_id
            else {"ServerSideEncryption": "AES256"}
        )
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            **encryption,
        )

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


class DocumentBackedStateStore:
    """Keep document bodies out of DynamoDB while preserving the StateStore API.

    The wrapped state record contains only a non-sensitive placeholder and an
    object key. Reads hydrate the original UTF-8 content and verify its hash.
    """

    def __init__(self, state: StateStore, documents: DocumentStore) -> None:
        self._state = state
        self._documents = documents
        self.name = f"{state.name}+{documents.name}"

    def _key(self, case_id: str, document_id: str) -> str:
        digest = sha256(document_id.encode("utf-8")).hexdigest()
        return f"cases/{case_id}/{digest}.txt"

    def put_case(self, case: CaseRecord, *, create_only: bool = False) -> None:
        previous_keys: set[str] = set()
        try:
            previous = self._state.get_case(case.case_id)
            previous_keys = {
                str(document.metadata["objectKey"])
                for document in previous.documents
                if "objectKey" in document.metadata
            }
        except RecordNotFound:
            pass
        stored_documents: list[EvidenceDocument] = []
        current_keys: set[str] = set()
        for document in case.documents:
            key = self._key(case.case_id, document.document_id)
            current_keys.add(key)
            self._documents.put(
                key,
                document.content.encode("utf-8"),
                content_type="text/plain; charset=utf-8",
            )
            stored_documents.append(
                document.model_copy(
                    update={
                        "content": "[Stored in encrypted temporary object storage.]",
                        "metadata": {
                            **document.metadata,
                            "objectKey": key,
                            "originalContentHash": document.content_hash,
                        },
                    }
                )
            )
        stored_case = case.model_copy(update={"documents": stored_documents})
        self._state.put_case(stored_case, create_only=create_only)
        for stale_key in previous_keys - current_keys:
            self._documents.delete(stale_key)

    def get_case(self, case_id: str) -> CaseRecord:
        case = self._state.get_case(case_id)
        hydrated: list[EvidenceDocument] = []
        for document in case.documents:
            key = document.metadata.get("objectKey")
            if not key:
                hydrated.append(document)
                continue
            content = self._documents.get(str(key)).decode("utf-8")
            expected_hash = document.metadata.get("originalContentHash")
            if expected_hash and sha256(content.encode("utf-8")).hexdigest() != expected_hash:
                raise RecordConflict(f"Document integrity check failed: {document.document_id}")
            hydrated.append(document.model_copy(update={"content": content}))
        return case.model_copy(update={"documents": hydrated})

    def delete_case(self, case_id: str) -> bool:
        try:
            case = self._state.get_case(case_id)
        except RecordNotFound:
            return False
        keys = [
            str(document.metadata["objectKey"])
            for document in case.documents
            if "objectKey" in document.metadata
        ]
        deleted = self._state.delete_case(case_id)
        if deleted:
            for key in keys:
                self._documents.delete(key)
        return deleted

    def put_run(self, run: RunRecord, *, create_only: bool = False) -> None:
        self._state.put_run(run, create_only=create_only)

    def get_run(self, run_id: str) -> RunRecord:
        return self._state.get_run(run_id)

    def list_runs(self, case_id: str) -> list[RunRecord]:
        return self._state.list_runs(case_id)

    def append_event(self, event: RunEvent) -> None:
        self._state.append_event(event)

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RunEvent]:
        return self._state.list_events(run_id, after_sequence=after_sequence)
