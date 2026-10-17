from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.loader import import_dataset


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="FieldSense dataset import")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Import a dataset root")
    run.add_argument("--path", required=True)
    run.add_argument("--dataset-version", default="sample-v1")

    sub.add_parser("migrate", help="Create database tables")

    args = parser.parse_args(argv)
    if args.cmd == "migrate":
        Base.metadata.create_all(bind=engine)
        print(json.dumps({"status": "migrated"}))
        return

    if args.cmd == "run":
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            summary = import_dataset(db, Path(args.path), args.dataset_version)
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
