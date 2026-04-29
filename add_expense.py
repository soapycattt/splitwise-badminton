#!/usr/bin/env python3
"""
Add badminton session expense to Splitwise.

Input format (stdin or file):
  date: 2026-04-26
  court: 500000
  shuttlecocks: 7
  shuttlecock_owner: Bùi Thanh Tùng
  host: Duong Ly
  players:
    Nhi Tran: 2
    Bùi Thanh Tùng: 1
    Nguyễn Minh Khuê: 1
"""

import json
import os
import sys
from datetime import datetime
import yaml
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.environ.get("SPLITWISE_API_KEY")
BASE_URL = "https://secure.splitwise.com/api/v3.0"
SCRIPT_DIR = Path(__file__).parent


def load_config():
    config_file = SCRIPT_DIR / "config.json"
    if not config_file.exists():
        return {"court_prices": {}, "shuttlecock_cost": 32000}
    with open(config_file) as f:
        return json.load(f)


CONFIG = load_config()


def load_members():
    members_file = SCRIPT_DIR / "members.txt"
    if not members_file.exists():
        print("Error: members.txt not found. Run fetch_members.py first.")
        sys.exit(1)

    members = {}
    group_id = None
    with open(members_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("# Group:"):
                group_id = int(line.split("id: ")[1].rstrip(")"))
            elif line and not line.startswith("#"):
                user_id, name = line.split(",", 1)
                members[name.lower()] = int(user_id)
    return group_id, members


def load_aliases():
    aliases_file = SCRIPT_DIR / "aliases.json"
    if not aliases_file.exists():
        return {}, [], ""

    with open(aliases_file) as f:
        data = json.load(f)

    aliases = {k.lower(): v.lower() for k, v in data.get("aliases", {}).items()}
    routing = data.get("_unmatched_routing", {})
    unmatched_people = [p.lower() for p in routing.get("people", [])]
    default_absorber = routing.get("default_absorber", "").lower()

    return aliases, unmatched_people, default_absorber


def resolve_user(name, members, aliases, unmatched_people, default_absorber):
    """Resolve a name to a Splitwise user ID. Returns (user_id, resolved_name, absorbed)."""
    key = name.lower().strip()

    if key in unmatched_people:
        if default_absorber in members:
            return members[default_absorber], default_absorber, True
        return None, None, False

    if key in aliases:
        resolved = aliases[key]
        if resolved in members:
            return members[resolved], resolved, False

    if key in members:
        return members[key], key, False

    for member_name, uid in members.items():
        if key in member_name or member_name in key:
            return uid, member_name, False

    print(f"Error: Cannot find user '{name}' in members.txt or aliases.json")
    print(f"Available members: {sorted(members.keys())}")
    sys.exit(1)


def create_expense(description, cost, group_id, payer_id, shares, date=None, dry_run=False):
    data = {
        "cost": f"{cost:.2f}",
        "description": description,
        "group_id": group_id,
        "currency_code": CONFIG.get("currency", "VND"),
    }
    if date:
        data["date"] = f"{date}T18:00:00Z"

    for i, (user_id, owed) in enumerate(shares):
        data[f"users__{i}__user_id"] = user_id
        data[f"users__{i}__paid_share"] = f"{cost:.2f}" if user_id == payer_id else "0.00"
        data[f"users__{i}__owed_share"] = f"{owed:.2f}"

    if dry_run:
        return {"id": "DRY_RUN", "data": data}

    resp = requests.post(
        f"{BASE_URL}/create_expense",
        headers={"Authorization": f"Bearer {API_KEY}"},
        data=data,
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("errors"):
        print(f"Error creating expense: {result['errors']}")
        sys.exit(1)

    return result["expenses"][0]


def main():
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
    aliases, unmatched_people, default_absorber = load_aliases()

    date = str(session["date"])
    shuttlecock_cost = CONFIG.get("shuttlecock_cost", 32000)

    # Auto-resolve court cost from day of week if not specified
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

    shuttlecock_count = int(session.get("shuttlecocks", 0))
    shuttlecock_owner_name = session.get("shuttlecock_owner", session.get("host", CONFIG.get("default_host", "")))
    host_name = session.get("host", CONFIG.get("default_host", ""))
    players = session["players"]

    shuttlecock_total = shuttlecock_count * shuttlecock_cost
    total_cost = court_cost + shuttlecock_total

    host_id, host_resolved, _ = resolve_user(host_name, members, aliases, unmatched_people, default_absorber)
    shuttle_owner_id, shuttle_resolved, _ = resolve_user(shuttlecock_owner_name, members, aliases, unmatched_people, default_absorber)

    total_ratio = sum(players.values())
    cost_per_unit = total_cost / total_ratio

    # Merge ratios for same user_id (handles absorbed players)
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

    # Round shares to 2 decimals, assign remainder to last person to match total exactly
    import math
    raw_shares = [(uid, owed) for uid, (owed, _) in user_shares.items()]
    shares = [(uid, math.floor(owed * 100) / 100) for uid, owed in raw_shares]
    remainder = total_cost - sum(owed for _, owed in shares)
    last_uid, last_owed = shares[-1]
    shares[-1] = (last_uid, round(last_owed + remainder, 2))

    print(f"\n{'='*50}")
    print(f"Badminton Session: {date}")
    print(f"{'='*50}")
    print(f"Court:        {court_cost:,.0f} VND")
    print(f"Shuttlecocks: {shuttlecock_count} x {shuttlecock_cost:,} = {shuttlecock_total:,.0f} VND")
    print(f"Total:        {total_cost:,.0f} VND")
    print(f"Host (payer): {host_name} → {host_resolved}")
    print(f"Shuttle owner: {shuttlecock_owner_name} → {shuttle_resolved}")
    print(f"\nSplit ({total_ratio} shares, {cost_per_unit:,.0f} VND/share):")
    for uid, (owed, names) in user_shares.items():
        label = ", ".join(names)
        print(f"  {label}: {owed:,.0f} VND")

    if absorbed_notes:
        print(f"\n⚠ Absorbed (not in Splitwise group):")
        for note in absorbed_notes:
            print(note)

    if dry_run:
        print(f"\n[DRY RUN] No expenses created.")
        return

    print(f"\n{'='*50}")
    confirm = input("Create expense(s)? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    day_name = session.get("day", datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower())
    shuttle_note = f" ({shuttlecock_count} sc)" if shuttlecock_count > 0 else ""
    desc = f"{day_name} {date}{shuttle_note}"
    expense = create_expense(desc, total_cost, group_id, host_id, shares, date=date)
    print(f"\n✓ Created: '{desc}' ({total_cost:,.0f} VND) — id: {expense['id']}")

    if shuttle_owner_id != host_id and shuttlecock_total > 0:
        reimburse_shares = [
            (host_id, shuttlecock_total),
            (shuttle_owner_id, 0),
        ]
        reimburse_desc = f"Shuttlecock reimbursement {date}"
        expense2 = create_expense(
            reimburse_desc, shuttlecock_total, group_id,
            shuttle_owner_id, reimburse_shares, date=date,
        )
        print(f"✓ Created: '{reimburse_desc}' ({shuttlecock_total:,.0f} VND) — id: {expense2['id']}")
        print(f"  ({host_resolved} owes {shuttle_resolved} for shuttlecocks)")

    print("\nDone!")


if __name__ == "__main__":
    main()
