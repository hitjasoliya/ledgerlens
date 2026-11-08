"""Schema bootstrap and operator commands.

LedgerLens keeps no upgrade path for older databases: an empty database gets the
current schema, a current one is accepted, and anything else is refused with an
instruction to wipe it.

    python -m common.migrate check
    python -m common.migrate reindex --document-id ID
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import uuid

import sqlalchemy as sa

from common.config import settings
from common.database import Base, engine
from common.models import Document, IngestionJob, utcnow

REVISION = "20261108_clean_schema"
_version = sa.Table(
    "ledgerlens_schema", sa.MetaData(),
    sa.Column("revision", sa.String(64), primary_key=True),
)


@contextmanager
def _locked_connection(bind):
    """A transaction that serializes schema work across processes."""
    with bind.connect() as connection:
        try:
            if bind.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                connection.begin()
                connection.execute(sa.text("SELECT pg_advisory_xact_lock(1738294661)"))
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def ensure_current(bind=None) -> None:
    bind = bind or engine
    with _locked_connection(bind) as connection:
        inspector = sa.inspect(connection)
        if inspector.has_table(_version.name):
            revisions = list(connection.scalars(sa.select(_version.c.revision)))
            if revisions == [REVISION]:
                return
        elif not set(inspector.get_table_names()):
            Base.metadata.create_all(connection)
            _version.create(connection)
            connection.execute(_version.insert().values(revision=REVISION))
            return
        raise RuntimeError(
            f"Database does not use the current LedgerLens schema ({REVISION}). "
            "LedgerLens keeps no upgrade path: wipe the database and start again."
        )


class ReindexRefused(ValueError):
    """The document can't be reindexed in its current state."""


def queue_reindex(db, document: Document) -> IngestionJob:
    """Queue a new version of a document for parsing; the caller commits.

    Allowed only for documents that are not already being processed or deleted,
    and whose original PDF is still in storage.
    """
    if document.status in ("queued", "processing", "deleting", "cleanup_pending"):
        raise ReindexRefused("Document already has active work or is being deleted")
    root = settings.UPLOAD_DIR.resolve()
    path = (root / document.storage_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ReindexRefused("The document's original PDF is missing from storage")
    document.version += 1
    document.status = "queued"
    document.error_message = None
    document.chunks_indexed = 0
    document.parser = document.embedding_model = document.embedding_dims = None
    job = IngestionJob(
        id=str(uuid.uuid4()), document_id=document.id, filename=document.filename,
        status="queued", stage="queued", document_version=document.version, attempts=0,
        created_at=utcnow(), updated_at=utcnow(),
    )
    db.add(job)
    return job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("check")
    indexing = commands.add_parser("reindex")
    indexing.add_argument("--document-id", required=True)
    args = parser.parse_args()
    ensure_current()
    if args.command == "reindex":
        from common.database import SessionLocal

        with SessionLocal() as db:
            document = db.get(Document, args.document_id, with_for_update=True)
            if document is None:
                raise SystemExit("Document not found")
            queue_reindex(db, document)
            db.commit()
        print("Reindex job queued")
    else:
        print(f"Schema current: {REVISION}")


if __name__ == "__main__":
    main()
