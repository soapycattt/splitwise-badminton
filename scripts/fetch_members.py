#!/usr/bin/env python3
"""Fetch Splitwise group members and save to members.txt"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests

PROJECT_DIR = Path(__file__).parent.parent
load_dotenv(PROJECT_DIR / ".env")
API_KEY = os.environ.get("SPLITWISE_API_KEY")
BASE_URL = "https://secure.splitwise.com/api/v3.0"


def get_groups():
    resp = requests.get(
        f"{BASE_URL}/get_groups",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    resp.raise_for_status()
    return resp.json()["groups"]


def main():
    if not API_KEY:
        print("Error: Set SPLITWISE_API_KEY environment variable")
        print("Get your key at: https://secure.splitwise.com/apps")
        sys.exit(1)

    groups = get_groups()

    print("\nYour groups:")
    for i, g in enumerate(groups):
        if g["id"] == 0:
            continue
        print(f"  [{i}] {g['name']} (id: {g['id']})")

    choice = int(input("\nSelect group number: "))
    group = groups[choice]

    members = []
    for m in group["members"]:
        first = m["first_name"] or ""
        last = m["last_name"] or ""
        name = f"{first} {last}".strip()
        members.append({"id": m["id"], "name": name})

    output_path = str(PROJECT_DIR / "members.txt")

    with open(output_path, "w") as f:
        f.write(f"# Group: {group['name']} (id: {group['id']})\n")
        f.write(f"# Format: user_id,display_name\n")
        for m in members:
            f.write(f"{m['id']},{m['name']}\n")

    print(f"\nSaved {len(members)} members to {output_path}")
    print("\nMembers:")
    for m in members:
        print(f"  {m['id']}: {m['name']}")


if __name__ == "__main__":
    main()
