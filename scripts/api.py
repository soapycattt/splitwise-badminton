"""Splitwise API helpers and shared utilities."""

import json
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent

load_dotenv(PROJECT_DIR / ".env")
API_KEY = os.environ.get("SPLITWISE_API_KEY")
BASE_URL = "https://secure.splitwise.com/api/v3.0"


def load_config():
    config_file = PROJECT_DIR / "config.json"
    if not config_file.exists():
        return {"court_prices": {}, "shuttlecock_cost": 32000}
    with open(config_file) as f:
        return json.load(f)


CONFIG = load_config()


def load_members():
    members_file = PROJECT_DIR / "members.txt"
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
    aliases_file = PROJECT_DIR / "aliases.json"
    if not aliases_file.exists():
        return {}, [], ""

    with open(aliases_file) as f:
        data = json.load(f)

    aliases = {k.lower(): v.lower() for k, v in data.get("aliases", {}).items()}
    routing = data.get("_unmatched_routing", {})
    unmatched_people = [p.lower() for p in routing.get("people", [])]
    default_absorber = routing.get("default_absorber", "").lower()
    host_identities = [p.lower() for p in routing.get("host_identities", [])]

    return aliases, unmatched_people, default_absorber, host_identities


def format_absorbed_details(absorbed_entries, host_resolved):
    """Build Splitwise expense details for guest shares routed to the host."""
    if not absorbed_entries:
        return None
    parts = [f"{name} ({amount:,.0f} VND)" for name, _, amount in absorbed_entries]
    return f"Guest shares absorbed by {host_resolved}: " + ", ".join(parts)


def resolve_user(name, members, aliases, unmatched_people, default_absorber, host_identities=None):
    """Resolve a name to a Splitwise user ID. Returns (user_id, resolved_name, absorbed)."""
    key = name.lower().strip()
    host_identities = host_identities or []

    if key in unmatched_people:
        if default_absorber in members:
            return members[default_absorber], default_absorber, True
        return None, None, False

    if key in aliases:
        resolved = aliases[key]
        if resolved in members:
            absorbed = resolved == default_absorber and key not in host_identities
            return members[resolved], resolved, absorbed

    if key in members:
        return members[key], key, False

    for member_name, uid in members.items():
        if key in member_name or member_name in key:
            return uid, member_name, False

    print(f"Error: Cannot find user '{name}' in members.txt or aliases.json")
    print(f"Available members: {sorted(members.keys())}")
    sys.exit(1)


def find_expense_by_description(group_id, description, date=None):
    """Search for an existing expense by exact description match, with date fallback.

    If exact match fails and date is provided, searches for expenses containing that date
    (handles description changes like adding shuttlecock count).
    """
    resp = requests.get(
        f"{BASE_URL}/get_expenses",
        headers={"Authorization": f"Bearer {API_KEY}"},
        params={"group_id": group_id, "limit": 200},
    )
    resp.raise_for_status()
    expenses = resp.json().get("expenses", [])

    for expense in expenses:
        if expense.get("description") == description and expense.get("deleted_at") is None:
            return expense["id"]

    if date:
        is_reimburse = "reimbursement" in description.lower()
        for expense in expenses:
            desc = expense.get("description", "")
            if expense.get("deleted_at") is not None:
                continue
            if date in desc:
                if is_reimburse and desc.startswith("Shuttlecock"):
                    return expense["id"]
                elif not is_reimburse and not desc.startswith("Shuttlecock"):
                    return expense["id"]

    return None


def _build_expense_data(description, cost, group_id, payer_id, shares, date=None, details=None):
    data = {
        "cost": f"{cost:.2f}",
        "description": description,
        "group_id": group_id,
        "currency_code": CONFIG.get("currency", "VND"),
    }
    if date:
        data["date"] = f"{date}T12:00:00+07:00"
    if details:
        data["details"] = details

    for i, (user_id, owed) in enumerate(shares):
        data[f"users__{i}__user_id"] = user_id
        data[f"users__{i}__paid_share"] = f"{cost:.2f}" if user_id == payer_id else "0.00"
        data[f"users__{i}__owed_share"] = f"{owed:.2f}"

    return data


def create_expense(description, cost, group_id, payer_id, shares, date=None, details=None, dry_run=False):
    data = _build_expense_data(description, cost, group_id, payer_id, shares, date, details)

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


def update_expense(expense_id, description, cost, group_id, payer_id, shares, date=None, details=None, dry_run=False):
    data = _build_expense_data(description, cost, group_id, payer_id, shares, date, details)

    if dry_run:
        return {"id": expense_id, "data": data}

    resp = requests.post(
        f"{BASE_URL}/update_expense/{expense_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        data=data,
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("errors"):
        print(f"Error updating expense: {result['errors']}")
        sys.exit(1)

    return result["expenses"][0]


def delete_expense(expense_id, dry_run=False):
    if dry_run:
        return True

    resp = requests.post(
        f"{BASE_URL}/delete_expense/{expense_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    resp.raise_for_status()
    result = resp.json()
    return result.get("success", False)
