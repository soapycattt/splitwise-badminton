#!/usr/bin/env python3
"""Add or update badminton session expense on Splitwise from a YAML artifact."""

import math
import sys
from datetime import datetime
import yaml

from api import (
    CONFIG, load_members, load_aliases, resolve_user, format_absorbed_details,
    find_expense_by_description, create_expense,
)


def main():
    from api import API_KEY
    if not API_KEY:
        print("Error: Set SPLITWISE_API_KEY in .env")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if args:
        with open(args[0]) as f:
            session = yaml.safe_load(f)
    else:
        print("Reading session from stdin (paste YAML, then Ctrl+D):")
        session = yaml.safe_load(sys.stdin)

    group_id, members = load_members()
    aliases, unmatched_people, default_absorber, host_identities = load_aliases()

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

    host_id, host_resolved, _ = resolve_user(
        host_name, members, aliases, unmatched_people, default_absorber, host_identities,
    )

    total_ratio = sum(players.values())
    cost_per_unit = total_cost / total_ratio

    user_shares = {}
    absorbed_entries = []

    for name, ratio in players.items():
        uid, resolved, absorbed = resolve_user(
            name, members, aliases, unmatched_people, default_absorber, host_identities,
        )
        owed = cost_per_unit * ratio
        if uid in user_shares:
            existing_owed, existing_names = user_shares[uid]
            user_shares[uid] = (existing_owed + owed, existing_names + [name])
        else:
            user_shares[uid] = (owed, [name])
        if absorbed:
            absorbed_entries.append((name, ratio, owed))

    raw_shares = [(uid, owed) for uid, (owed, _) in user_shares.items()]
    if host_id not in [uid for uid, _ in raw_shares]:
        raw_shares.insert(0, (host_id, 0))
    shares = [(uid, math.floor(owed * 100) / 100) for uid, owed in raw_shares]
    remainder = total_cost - sum(owed for _, owed in shares)
    last_uid, last_owed = shares[-1]
    shares[-1] = (last_uid, round(last_owed + remainder, 2))

    absorbed_details = format_absorbed_details(absorbed_entries, host_resolved)

    print(f"\n{'='*50}")
    print(f"Badminton Session: {date}")
    print(f"{'='*50}")
    print(f"Court:        {court_cost:,.0f} VND")
    print(f"Shuttlecocks: {shuttlecock_count} x {shuttlecock_cost:,} = {shuttlecock_total:,.0f} VND")
    print(f"Total:        {total_cost:,.0f} VND")
    print(f"Host (payer): {host_name} → {host_resolved}")
    if shuttlecock_owners:
        for owner, count in shuttlecock_owners.items():
            _, resolved, _ = resolve_user(
                owner, members, aliases, unmatched_people, default_absorber, host_identities,
            )
            print(f"Shuttle owner: {owner} → {resolved} ({count} sc)")
    else:
        print(f"Shuttle owner: {host_name} → {host_resolved} (0 sc)")
    print(f"\nSplit ({total_ratio} shares, {cost_per_unit:,.0f} VND/share):")
    for uid, (owed, names) in user_shares.items():
        label = ", ".join(names)
        print(f"  {label}: {owed:,.0f} VND")

    if absorbed_entries:
        print(f"\n⚠ Absorbed into {host_resolved}:")
        for name, ratio, owed in absorbed_entries:
            print(f"  {name} (ratio {ratio}): {owed:,.0f} VND")
        print(f"Details: {absorbed_details}")

    if dry_run:
        print(f"\n[DRY RUN] No expenses created.")
        return

    day_name = session.get("day", datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower())
    shuttle_note = f" ({shuttlecock_count} sc)" if shuttlecock_count > 0 else ""
    desc = f"{day_name} {date}{shuttle_note}"

    existing_id = find_expense_by_description(group_id, desc)
    if existing_id:
        print(f"\n⚠ Expense '{desc}' already exists (id: {existing_id}). Use update_expense.py to modify.")
        sys.exit(1)

    print(f"\n{'='*50}")
    confirm = input("Create expense(s)? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    expense = create_expense(desc, total_cost, group_id, host_id, shares, date=date, details=absorbed_details)
    print(f"\n✓ Created: '{desc}' ({total_cost:,.0f} VND) — id: {expense['id']}")

    for owner_name, owner_count in shuttlecock_owners.items():
        owner_id, owner_resolved, _ = resolve_user(
            owner_name, members, aliases, unmatched_people, default_absorber, host_identities,
        )
        owner_total = owner_count * shuttlecock_cost
        if owner_id != host_id and owner_total > 0:
            reimburse_shares = [
                (host_id, owner_total),
                (owner_id, 0),
            ]
            reimburse_desc = f"Shuttlecock reimbursement {date} ({owner_resolved})"
            expense2 = create_expense(
                reimburse_desc, owner_total, group_id,
                owner_id, reimburse_shares, date=date,
            )
            print(f"✓ Created: '{reimburse_desc}' ({owner_total:,.0f} VND) — id: {expense2['id']}")
            print(f"  ({host_resolved} owes {owner_resolved} for {owner_count} shuttlecocks)")

    print("\nDone!")


if __name__ == "__main__":
    main()
