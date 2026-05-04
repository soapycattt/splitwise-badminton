#!/usr/bin/env python3
"""Update an existing badminton session expense on Splitwise from a YAML artifact.

Searches by expense description. If not found, exits with error (use add_expense.py to create).
"""

import math
import sys
from datetime import datetime
import yaml

from api import (
    CONFIG, load_members, load_aliases, resolve_user,
    find_expense_by_description, update_expense,
)


def main():
    from api import API_KEY
    if not API_KEY:
        print("Error: Set SPLITWISE_API_KEY in .env")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print("Usage: update_expense.py <artifact.yaml> [--dry-run]")
        sys.exit(1)

    with open(args[0]) as f:
        session = yaml.safe_load(f)

    group_id, members = load_members()
    aliases, unmatched_people, default_absorber = load_aliases()

    date = str(session["date"])
    shuttlecock_cost = CONFIG.get("shuttlecock_cost", 32000)

    if "court" in session:
        court_cost = float(session["court"])
    else:
        day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower()
        court_prices = CONFIG.get("court_prices", {})
        if day_name in court_prices:
            court_cost = float(court_prices[day_name])
        else:
            print(f"Error: No court price for {day_name}. Set 'court' in YAML or add to config.json")
            sys.exit(1)

    host_name = session.get("host", CONFIG.get("default_host", ""))
    players = session["players"]

    if "shuttlecock_owners" in session:
        shuttlecock_owners = {name: int(count) for name, count in session["shuttlecock_owners"].items()}
        shuttlecock_count = sum(shuttlecock_owners.values())
    else:
        shuttlecock_count = int(session.get("shuttlecocks", 0))
        owner_name = session.get("shuttlecock_owner", host_name)
        shuttlecock_owners = {owner_name: shuttlecock_count} if shuttlecock_count > 0 else {}

    shuttlecock_total = shuttlecock_count * shuttlecock_cost
    total_cost = court_cost + shuttlecock_total

    host_id, host_resolved, _ = resolve_user(host_name, members, aliases, unmatched_people, default_absorber)

    total_ratio = sum(players.values())
    cost_per_unit = total_cost / total_ratio

    user_shares = {}
    absorbed_notes = []

    for name, ratio in players.items():
        uid, resolved, absorbed = resolve_user(name, members, aliases, unmatched_people, default_absorber)
        owed = cost_per_unit * ratio
        if uid in user_shares:
            existing_owed, existing_names = user_shares[uid]
            user_shares[uid] = (existing_owed + owed, existing_names + [name])
        else:
            user_shares[uid] = (owed, [name])
        if absorbed:
            absorbed_notes.append(f"  {name} (ratio {ratio}) → absorbed into {default_absorber}")

    raw_shares = [(uid, owed) for uid, (owed, _) in user_shares.items()]
    if host_id not in [uid for uid, _ in raw_shares]:
        raw_shares.insert(0, (host_id, 0))
    shares = [(uid, math.floor(owed * 100) / 100) for uid, owed in raw_shares]
    remainder = total_cost - sum(owed for _, owed in shares)
    last_uid, last_owed = shares[-1]
    shares[-1] = (last_uid, round(last_owed + remainder, 2))

    day_name = session.get("day", datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower())
    shuttle_note = f" ({shuttlecock_count} sc)" if shuttlecock_count > 0 else ""
    desc = f"{day_name} {date}{shuttle_note}"

    print(f"\n{'='*50}")
    print(f"Badminton Session: {date}")
    print(f"{'='*50}")
    print(f"Total:        {total_cost:,.0f} VND")
    print(f"Description:  {desc}")

    existing_id = find_expense_by_description(group_id, desc)
    if not existing_id:
        print(f"\n✗ No existing expense found with description '{desc}'")
        print("  Use add_expense.py to create it first.")
        sys.exit(1)

    print(f"⚡ Found expense id: {existing_id}")
    print(f"\nSplit ({total_ratio} shares, {cost_per_unit:,.0f} VND/share):")
    for uid, (owed, names) in user_shares.items():
        label = ", ".join(names)
        print(f"  {label}: {owed:,.0f} VND")

    if absorbed_notes:
        print(f"\n⚠ Absorbed:")
        for note in absorbed_notes:
            print(note)

    if dry_run:
        print(f"\n[DRY RUN] No expenses updated.")
        return

    confirm = input(f"\nUpdate expense? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    expense = update_expense(existing_id, desc, total_cost, group_id, host_id, shares, date=date)
    print(f"\n✓ Updated: '{desc}' ({total_cost:,.0f} VND) — id: {expense['id']}")

    for owner_name, owner_count in shuttlecock_owners.items():
        owner_id, owner_resolved, _ = resolve_user(owner_name, members, aliases, unmatched_people, default_absorber)
        owner_total = owner_count * shuttlecock_cost
        if owner_id != host_id and owner_total > 0:
            reimburse_shares = [
                (host_id, owner_total),
                (owner_id, 0),
            ]
            reimburse_desc = f"Shuttlecock reimbursement {date} ({owner_resolved})"
            existing_reimburse_id = find_expense_by_description(group_id, reimburse_desc)

            if existing_reimburse_id:
                expense2 = update_expense(
                    existing_reimburse_id, reimburse_desc, owner_total, group_id,
                    owner_id, reimburse_shares, date=date,
                )
                print(f"✓ Updated: '{reimburse_desc}' ({owner_total:,.0f} VND) — id: {expense2['id']}")
            else:
                from api import create_expense
                expense2 = create_expense(
                    reimburse_desc, owner_total, group_id,
                    owner_id, reimburse_shares, date=date,
                )
                print(f"✓ Created: '{reimburse_desc}' ({owner_total:,.0f} VND) — id: {expense2['id']}")
            print(f"  ({host_resolved} owes {owner_resolved} for {owner_count} shuttlecocks)")

    print("\nDone!")


if __name__ == "__main__":
    main()
