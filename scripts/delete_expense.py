#!/usr/bin/env python3
"""Delete a badminton session expense from Splitwise by searching its description.

Can delete by YAML artifact (uses naming convention) or by explicit description string.
"""

import sys
from datetime import datetime
import yaml

from api import (
    CONFIG, API_KEY, load_members, load_aliases, resolve_user,
    find_expense_by_description, delete_expense,
)


def main():
    if not API_KEY:
        print("Error: Set SPLITWISE_API_KEY in .env")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print("Usage: delete_expense.py <artifact.yaml> [--dry-run]")
        print("       delete_expense.py --desc 'sunday 2026-04-12 (13 sc)' [--dry-run]")
        sys.exit(1)

    group_id, members = load_members()
    aliases, unmatched_people, default_absorber = load_aliases()

    if args[0] == "--desc":
        desc = args[1]
        shuttlecock_owners = {}
        date = ""
    else:
        with open(args[0]) as f:
            session = yaml.safe_load(f)

        date = str(session["date"])
        shuttlecock_cost = CONFIG.get("shuttlecock_cost", 32000)

        if "shuttlecock_owners" in session:
            shuttlecock_owners = {name: int(count) for name, count in session["shuttlecock_owners"].items()}
            shuttlecock_count = sum(shuttlecock_owners.values())
        else:
            shuttlecock_count = int(session.get("shuttlecocks", 0))
            owner_name = session.get("shuttlecock_owner", session.get("host", ""))
            shuttlecock_owners = {owner_name: shuttlecock_count} if shuttlecock_count > 0 else {}

        day_name = session.get("day", datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower())
        shuttle_note = f" ({shuttlecock_count} sc)" if shuttlecock_count > 0 else ""
        desc = f"{day_name} {date}{shuttle_note}"

    existing_id = find_expense_by_description(group_id, desc)
    if not existing_id:
        print(f"✗ No expense found with description '{desc}'")
        sys.exit(1)

    print(f"Found expense: '{desc}' — id: {existing_id}")

    if dry_run:
        print("[DRY RUN] Would delete this expense.")
        return

    confirm = input("Delete this expense? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    delete_expense(existing_id)
    print(f"✓ Deleted: '{desc}' — id: {existing_id}")

    # Also delete associated reimbursements
    host_name = session.get("host", CONFIG.get("default_host", "")) if date else ""
    host_id, _, _ = resolve_user(host_name, members, aliases, unmatched_people, default_absorber) if host_name else (None, None, None)

    for owner_name, owner_count in shuttlecock_owners.items():
        owner_id, owner_resolved, _ = resolve_user(owner_name, members, aliases, unmatched_people, default_absorber)
        if host_id and owner_id != host_id and owner_count > 0:
            reimburse_desc = f"Shuttlecock reimbursement {date} ({owner_resolved})"
            reimburse_id = find_expense_by_description(group_id, reimburse_desc)
            if reimburse_id:
                delete_expense(reimburse_id)
                print(f"✓ Deleted reimbursement: '{reimburse_desc}' — id: {reimburse_id}")

    print("\nDone!")


if __name__ == "__main__":
    main()
