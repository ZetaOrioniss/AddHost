# HOSTSCTL >

**Author:** ZetaOrioniss\
**Version:** 1.0

**HOSTSCTL** is an interactive Python console for managing `/etc/hosts` entries during penetration testing and CTF sessions. Add, remove, edit, and search host mappings without ever manually touching the file — and with automatic backups before every write operation.

> ⚠️ **Disclaimer**: This tool is intended for use on systems you own or have explicit authorization to administrate. The author declines all responsibility for any misuse.

![screenshot](https://github.com/ZetaOrioniss/hostsctl/blob/main/assets/example.png)

---

## 1. Why HOSTSCTL?

During a pentest or CTF, `/etc/hosts` gets edited constantly — adding machine hostnames, virtual host entries for web enumeration, or Active Directory records. The usual workflow is painful: `sudo nano /etc/hosts`, hunt for the right line, edit carefully, save, and hope you didn't break anything.

HOSTSCTL replaces that with a purpose-built console:

* **One-command operations** — add, remove, or edit entries inline without opening any editor.
* **Metasploit-style UX** — familiar prompt, full `Tab` auto-completion on every command and hostname.
* **Non-destructive** — system entries (loopback, IPv6 defaults) are displayed but never touched. Every write operation creates a timestamped backup automatically.
* **Instant search** — find any entry by IP, hostname, or alias across the entire file.
* **Rollback anytime** — restore any previous state of `/etc/hosts` in two keystrokes.

---

## 2. Installation & Dependencies

### Prerequisites

Pure Python 3 — no external libraries required.

Write operations require **root privileges** (or `sudo`). The console will still start and let you list/search without root, displaying a `[ro]` indicator in the prompt.

### Installation

```bash
git clone https://github.com/ZetaOrioniss/hostsctl.git
cd hostsctl
chmod +x hostsctl.py
```

### Usage

```bash
# Read-only (listing, search)
./hostsctl.py

# With write access (add, remove, edit, restore)
sudo ./hostsctl.py
```

---

## 3. Usage Guide 🖥️

### Prompt

```
hostsctl [rw] >     ← root / write access
hostsctl [ro] >     ← read-only (no sudo)
```

The prompt updates in real time. If you restart with `sudo`, it switches to `[rw]` automatically.

---

## 4. Command Reference

### 📋 Listing & Search

| Command | Description |
|---|---|
| `list` / `ls` | Show all entries — managed and system — in a formatted table |
| `list managed` | Show only entries added by hostsctl |
| `list system` | Show only pre-existing system entries (read-only display) |
| `search <term>` | Search by IP, hostname, or alias (partial match) |
| `show <hostname>` | Display full details for a single entry |

### ➕ Adding Entries

| Command | Description |
|---|---|
| `add <ip> <hostname> [alias…] [--comment "…"]` | Add an entry in a single line |
| `add` | Launch the interactive step-by-step wizard |

**Inline examples:**
```bash
add 10.10.11.25 board.htb
add 10.10.11.25 board.htb crm.board.htb --comment "HackTheBox BoardLight"
add 192.168.1.100 dc01.corp.local dc01 --comment "Domain Controller"
```

**Wizard** (`add` with no arguments):
```
IP address: 10.10.11.25
Hostname:   board.htb
Aliases:    crm.board.htb
Comment:    HackTheBox BoardLight

Preview:  10.10.11.25    board.htb    crm.board.htb  # HackTheBox BoardLight  # [hostsctl]
Confirm? [Y/n]
```

### ❌ Removing Entries

| Command | Description |
|---|---|
| `remove <hostname>` | Remove an entry by hostname or alias |
| `remove` | Launch the interactive numbered picker |

### ✏️ Editing Entries

| Command | Description |
|---|---|
| `edit <hostname>` | Interactive wizard — shows current values, blank = keep |
| `edit <hostname> --ip <new_ip>` | Update the IP only |
| `edit <hostname> --name <new_name>` | Rename the hostname |
| `edit <hostname> --comment "…"` | Update the comment |

Flags can be combined:
```bash
edit board.htb --ip 10.10.11.99 --comment "Updated IP"
```

### 💾 Backups

| Command | Description |
|---|---|
| `backup` | Create a manual snapshot now |
| `backups` / `backup list` | List all saved backups with date and size |
| `restore` | Interactive picker with confirmation prompt |
| `restore <n>` | Restore backup number `n` directly |

Backups are stored in `~/.hostsctl/backups/` and rotated automatically (20 most recent kept). A backup is **always created automatically** before any write operation (add, remove, edit, restore).

### 🔧 Other

| Command | Description |
|---|---|
| `clear` | Clear the screen |
| `help` | Show the full command reference |
| `exit` / `quit` | Exit the console |

---

## 5. Workflow Examples

### HTB / CTF — Add a machine

```
hostsctl [rw] > add 10.10.11.25 board.htb --comment "BoardLight"
  ✔  Added: board.htb → 10.10.11.25
```

### VHost enumeration — Add multiple aliases at once

```
hostsctl [rw] > add 10.10.11.25 board.htb crm.board.htb portal.board.htb
  ✔  Added: board.htb → 10.10.11.25
```

### Machine IP changed after reset — Edit in place

```
hostsctl [rw] > edit board.htb --ip 10.10.11.38
  ✔  Updated: board.htb
```

### Find all entries for a subnet

```
hostsctl [rw] > search 10.10.11
```

### Undo a broken edit

```
hostsctl [rw] > restore
  #  BACKUP               DATE                  SIZE
  1. hosts_20250518_143201  2025-05-18 14:32:01   847 B
  2. hosts_20250518_141055  2025-05-18 14:10:55   802 B
  ...
Enter backup number to restore: 1
  [!] This will overwrite /etc/hosts with: hosts_20250518_143201
  Confirm? [y/N] y
  ✔  Restored: hosts_20250518_143201
```

---

## 6. File Format & Safety

Entries added by HOSTSCTL are tagged with an inline marker (`# [hostsctl]`) so they can be safely identified, edited, and removed without touching anything else in the file.

**Your existing system entries are never modified.** The tool reads them, displays them as `[sys]`, and leaves them untouched.

```
# /etc/hosts — example after using HOSTSCTL

127.0.0.1    localhost                          ← [sys] never touched
::1          localhost ip6-localhost ip6-loopback

# ── hostsctl managed entries ───────────────────
10.10.11.25  board.htb  crm.board.htb  # BoardLight  # [hostsctl]
10.10.10.3   cronos.htb                              # [hostsctl]
```

---

## 7. Backup System

| Detail | Value |
|---|---|
| Location | `~/.hostsctl/backups/` |
| Format | `hosts_YYYYMMDD_HHMMSS` |
| Trigger | Automatic before every write + manual `backup` command |
| Retention | 20 most recent (older ones deleted automatically) |
| Restore safety | Current state is backed up before any restore |

---

## 8. Tab Completion

Every command, sub-command, flag, and existing hostname supports `Tab` completion:

```
list <Tab>        → managed  system
remove <Tab>      → board.htb  cronos.htb  …
edit board<Tab>   → board.htb
edit board.htb <Tab>  → --ip  --name  --comment
backup <Tab>      → list
```

---

## Upcoming Features

* `--alias add/remove` flag to manage aliases independently
* `import <file>` — bulk import from a hosts file
* `export` — export managed entries only
* Color-coded IP ranges (10.x, 192.168.x, etc.)
* Shell one-liner mode: `hostsctl add 10.10.11.25 board.htb` (non-interactive)
