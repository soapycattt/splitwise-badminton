---
name: splitwise-badminton
description: Add badminton session expenses to Splitwise from poll screenshots or text input. Use when the user mentions badminton expense, splitting court costs, shuttlecock costs, Sunday/Saturday/Tuesday session, poll results with player names and +1/+2 ratios, or wants to create a Splitwise expense for their badminton group. Also triggers on "add expense", "split badminton", "session cost", "cầu lông", or any mention of court booking payments.
---

# Splitwise Badminton Expense Skill

Generate a session YAML file from user input (screenshot or text), preview the split, then execute the expense creation script.

## Location

All scripts and config live at: `/Users/triet.lequang/Documents/personal/splitwise/`

## Input

The user provides:
1. **Screenshot(s)** from a poll app showing:
   - Main voter list (e.g. "11 votes for CN 6-8PM") — these are the players
   - +1 voter list (e.g. "3 votes for CN +1") — these players have ratio 2
   - If there's a +2 list, those players have ratio 3
2. **Text info** (user tells you, or you ask):
   - Date of the session (or infer from poll title: CN = Sunday, T7 = Saturday, T3 = Tuesday)
   - Shuttlecock count
   - Who paid for shuttlecocks
   - Any overrides (different host, someone already handled reimbursement, etc.)

### What you must ask if not provided:
- How many shuttlecocks?
- Who paid for shuttlecocks?

### What you do NOT need to ask:
- Court price (auto-resolved from day of week via `config.json`)
- Host (default: Duong Ly)
- Player ratios (derived from poll screenshots: main list = ratio 1, +1 list = ratio 2, +2 list = ratio 3)

## Process

1. **Parse input** — Extract player names and ratios from screenshots:
   - All voters in main poll → ratio 1
   - Voters also appearing in +1 poll → ratio 2
   - Voters also appearing in +2 poll → ratio 3
   - Players ONLY in +1/+2 but NOT in main list are still included (they voted via +1 only)

2. **Resolve names** — Match poll names against `aliases.json` then `members.txt`:
   - Check `aliases.json` first (handles Vietnamese name variations)
   - If name maps to a Splitwise member → use that member
   - If name is in `_unmatched_routing.people` → share absorbed into default absorber (Duong Ly)
   - If name isn't found anywhere → **ask the user** before proceeding

3. **Generate session YAML** — Save to `artifacts/YYYYMMDD_day.yaml`:
   ```yaml
   date: 2026-04-26
   day: sunday
   shuttlecocks: 7
   shuttlecock_owner: Bùi Thanh Tùng
   host: Duong Ly
   players:
     # +1 voters (ratio 2)
     Nhi Tran: 2
     Dương Nghi: 2
     # Regular voters (ratio 1)
     Bùi Thanh Tùng: 1
     Nguyễn Minh Khuê: 1
   ```
   - Omit `court` field — auto-resolved from `config.json` by day of week
   - If shuttlecock owner = host → no reimbursement expense created
   - Add YAML comments noting absorbed/aliased players

4. **Preview** — Dry-run and show the user a formatted summary:
   ```bash
   cd /Users/triet.lequang/Documents/personal/splitwise
   .venv/bin/python add_expense.py artifacts/YYYYMMDD_day.yaml --dry-run
   ```
   Show: total, per-person breakdown, absorbed players, expense title.

5. **Confirm and execute** — Only after user says yes:
   ```bash
   echo "y" | .venv/bin/python add_expense.py artifacts/YYYYMMDD_day.yaml
   ```

## Output

- **Splitwise expense** titled `{day} {date} ({N} sc)` — paid by host, split by ratio
- **Optional reimbursement expense** if shuttlecock_owner ≠ host (titled `Shuttlecock reimbursement {date}`)
- **Artifact YAML** saved for record-keeping

## Key Config Files

| File | Purpose |
|------|---------|
| `config.json` | Court prices by day, shuttlecock cost (30k), default host, group ID, currency |
| `aliases.json` | Name mapping (poll name → Splitwise name) + unmatched guest routing |
| `members.txt` | Splitwise user IDs and display names (fetched from API) |
| `.env` | API credentials (SPLITWISE_API_KEY) |

## Rules

- Court prices: Sunday 640k, Saturday 300k, Tuesday 135k
- Shuttlecock: 30,000 VND each
- Default host: Duong Ly (id: 72800572)
- Default absorber for unmatched guests: Duong Ly
- If shuttlecock_owner ≠ host → auto-creates reimbursement expense
- Expense title format: `{day} {date} ({N} sc)`
- Rounding: floor to 2 decimals, remainder added to last person

## Common Scenarios

**Shuttlecock owner already reimbursed themselves on Splitwise:**
Set `shuttlecock_owner` to the host name (Duong Ly) in the YAML to skip auto-reimbursement.

**New player not in aliases:**
Ask user which Splitwise member they map to. Update `aliases.json` with the mapping.

**Guest not in Splitwise group:**
Add their lowercase name to `_unmatched_routing.people` in `aliases.json`. Their share gets absorbed into Duong Ly.

**Someone brings +1 but isn't in the main voter list:**
They still get included. Their name appears only in the +1 screenshot → ratio 2.

**Multiple sessions on same date:**
Append a suffix to the artifact filename, e.g. `session_2026-04-26_2.yaml`.
