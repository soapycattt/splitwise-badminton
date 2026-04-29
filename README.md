# Splitwise Badminton Expense Tool

Automate splitting badminton session costs on Splitwise from poll screenshots.

## What it does

- Reads player names and +1/+2 ratios from poll screenshots
- Auto-calculates court price by day of week
- Splits total (court + shuttlecocks) by ratio
- Creates Splitwise expense with correct shares per person
- Handles guests not in the Splitwise group (absorbed into host)

## Setup

### 1. Get Splitwise API Key

1. Go to https://secure.splitwise.com/apps
2. Click "Register your application"
3. Fill in any app name (e.g. "Badminton Splitter"), homepage URL can be `http://localhost`
4. After creating, copy the **API Key** shown on the app page

### 2. Environment Setup

```bash
cd /path/to/this/folder

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Create .env from example
cp .env.example .env
```

Edit `.env` and paste your API key:
```
SPLITWISE_API_KEY=your_key_here
```

### 3. Fetch Group Members

```bash
python fetch_members.py
```

This lists your Splitwise groups. Pick the badminton group and it saves `members.txt` with all member IDs.

### 4. Test It

```bash
# Dry run with an existing session
python add_expense.py artifacts/20260426_sunday.yaml --dry-run
```

## Usage (Manual)

Create a YAML file in `artifacts/`:

```yaml
date: 2026-04-26
day: sunday
shuttlecocks: 7
shuttlecock_owner: Bùi Thanh Tùng
host: Duong Ly
players:
  Nhi Tran: 2        # +1 voter (ratio 2)
  Bùi Thanh Tùng: 1  # regular voter (ratio 1)
  Nguyễn Minh Khuê: 1
```

Then run:
```bash
python add_expense.py artifacts/20260426_sunday.yaml
```

## Usage (Claude Code Skill)

### Prerequisites

- [Claude Code](https://claude.ai/claude-code) installed
- This repo cloned/copied to your machine

### Skill location

The skill is a project skill at `.claude/skills/splitwise-badminton.md`. No installation needed — just open this folder in Claude Code and it's available automatically.

### Use it

1. Open the Facebook Messenger group poll and take screenshots of:
   - **Main session poll item** (e.g. "CN 6-8PM") — shows who's playing
   - **+1 poll item** (e.g. "CN +1") — shows who's bringing a guest
   - **+2 poll item** (if applicable) — shows who's bringing 2 guests

2. In Claude Code, paste the screenshots and say something like:
   > "add badminton expense, 5 sc paid by Tung"

Claude will:
1. Read player names from the poll screenshots
2. Assign ratios (main voters = 1, +1 voters = 2, +2 voters = 3)
3. Generate the YAML
4. Show you a preview
4. Execute after you confirm

## Config

### `config.json`

```json
{
  "court_prices": {
    "sunday": 640000,
    "saturday": 300000,
    "tuesday": 135000
  },
  "shuttlecock_cost": 30000,
  "default_host": "duong ly",
  "group_id": 82856058,
  "currency": "VND"
}
```

### `aliases.json`

Maps poll names to Splitwise display names. Add new mappings when someone's poll name doesn't match their Splitwise name:

```json
{
  "aliases": {
    "nhi tran": "nhity",
    "dương nghi": "nghi nghi"
  }
}
```

### Unmatched guests

People not in the Splitwise group have their share absorbed into the default absorber (Duong Ly). Add them to `_unmatched_routing.people` in `aliases.json`.

## File Structure

```
.
├── add_expense.py       # Main script
├── fetch_members.py     # Fetch group members from API
├── config.json          # Court prices, defaults
├── aliases.json         # Name mapping + guest routing
├── members.txt          # Splitwise user IDs (auto-generated)
├── artifacts/           # Session YAML files (records)
├── .claude/skills/      # Claude Code project skill (auto-detected)
├── .env                 # API credentials (git-ignored)
├── .env.example         # Template for .env
└── requirements.txt     # Python dependencies
```
