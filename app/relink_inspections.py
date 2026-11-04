"""Apply the linking rules to inspection submissions already stored (after the rules change).

    python -m app.relink_inspections --operator-id UUID [--dry-run]

Lists every submission whose store changes, counts those whose order alone changes (an order
synced after its submission arrived), and moves photos to the new company.
Nothing is fetched from GoCanvas. Safe to rerun: a second run changes nothing.
"""

import argparse
import logging
import sys
import uuid

from app.db.session import SessionLocal
from app.models import Location, Tenant, TenantKind
from app.services.inspections import relink_submissions

log = logging.getLogger("app.relink_inspections")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--operator-id", required=True, type=uuid.UUID)
    parser.add_argument("--dry-run", action="store_true", help="list the changes, save nothing")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        operator = db.get(Tenant, args.operator_id)
        if operator is None or operator.kind is not TenantKind.operator:
            log.error("No operator %s", args.operator_id)
            return 1

        def name(location_id: uuid.UUID | None) -> str:
            location = db.get(Location, location_id) if location_id else None
            return (location.pestpac_company or str(location.id)) if location else "unlinked"

        changed = relink_submissions(db, operator.id)
        moved = [(sub, previous) for sub, previous in changed if sub.location_id != previous]
        for submission, previous in moved:
            log.info(
                "%s: %s -> %s",
                submission.gocanvas_submission_id,
                name(previous),
                name(submission.location_id),
            )
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    log.info(
        "%d submissions %s: %d to another store, %d only their service order",
        len(changed),
        "would change" if args.dry_run else "changed",
        len(moved),
        len(changed) - len(moved),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
