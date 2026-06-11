# hostsctl

```
╔══════════════════════════════════════════════════════════════╗
║                          HOSTsCTL                            ║
╚══════════════════════════════════════════════════════════════╝
```

A fast, scriptable `/etc/hosts` manager with both a one-liner CLI and an interactive console.
Built for pentesters, CTF players, and sysadmins who add and remove hosts constantly.

**Author:** [@ZetaOrioniss](https://github.com/ZetaOrioniss) — **Version:** v1.1

---

## Features

- **One-liner CLI** — add, remove, edit, search without entering a console
- **Interactive console** — readline shell with tab-completion and wizards
- **Auto-backup** — every write operation snapshots `/etc/hosts` first
- **Backup rotation** — keeps the 20 most recent backups automatically
- **Managed vs system entries** — tracks which lines hostsctl wrote vs pre-existing ones
- **Aliases support** — multiple names per IP in a single entry
- **Inline comments** — annotate entries (`-c "HackTheBox Season 5"`)
- **`--force` flag** — skip all confirmation prompts for scripting/automation

---

## Requirements

- Python 3.10+
- Root / `sudo` access (read-only mode still works without it)

No third-party dependencies — standard library only.

---

## Installation

```bash
# Clone or download
git clone https://github.com/ZetaOrioniss/hostsctl
cd hostsctl

# Make executable
chmod +x hostsctl.py

# Optional: install system-wide
sudo cp hostsctl.py /usr/local/bin/hostsctl
```

---

## Usage

### Two modes

| Mode | How to invoke | When to use |
|---|---|---|
| **CLI** | `hostsctl <command> [args]` | One-off operations, scripts, aliases |
| **Console** | `hostsctl` (no args) | Interactive session, wizards, tab-complete |

---

## CLI Reference

### List entries

```bash
sudo hostsctl list                  # all entries (managed + system)
sudo hostsctl list managed          # only hostsctl-managed entries
sudo hostsctl list system           # only pre-existing system entries
sudo hostsctl ls                    # alias for list
```

### Add an entry

```bash
sudo hostsctl add <ip> <hostname> [aliases…] [-c "comment"]

# Examples
sudo hostsctl add 10.10.10.5 machine.htb
sudo hostsctl add 10.10.10.5 machine.htb admin.machine.htb -c "HackTheBox"
sudo hostsctl add 192.168.1.100 dev.local api.dev.local web.dev.local -c "dev env"
```

### Remove an entry

```bash
sudo hostsctl remove <hostname>             # prompts for confirmation
sudo hostsctl remove <hostname> --force     # no prompt (for scripts)
sudo hostsctl rm <hostname>                 # alias
sudo hostsctl del <hostname>                # alias
```

### Edit an entry

```bash
sudo hostsctl edit <hostname> --ip <new-ip>
sudo hostsctl edit <hostname> --name <new-hostname>
sudo hostsctl edit <hostname> -c "new comment"

# Combine flags in one shot
sudo hostsctl edit machine.htb --ip 10.10.10.99 --name newbox.htb -c "retired"

# No flags → launches interactive wizard
sudo hostsctl edit machine.htb
```

### Search & inspect

```bash
sudo hostsctl search <term>         # match on IP, hostname, or alias
sudo hostsctl show <hostname>       # detailed view of one entry
```

### Backups

```bash
sudo hostsctl backup                # create a manual backup now
sudo hostsctl backup list           # list all saved backups
sudo hostsctl backups               # alias for backup list

sudo hostsctl restore               # interactive picker
sudo hostsctl restore <n>           # restore backup by index number
sudo hostsctl restore --list        # print backup list and exit
sudo hostsctl restore <n> --force   # restore without confirmation
```

Backups are stored in `~/.hostsctl/backups/` and named `hosts_YYYYMMDD_HHMMSS`.

---

## Interactive Console

Launch by running `hostsctl` with no arguments:

```
hostsctl [rw] > _
```

The prompt shows `[rw]` (read-write) or `[ro]` (read-only) depending on your permissions.

All CLI commands work inside the console too. Additional console-only commands:

| Command | Description |
|---|---|
| `clear` | Clear the screen |
| `help` | Show command reference |
| `exit` / `quit` | Exit the console |

Tab-completion is available for commands, subcommands, and hostnames.

### Interactive wizards

Some commands open a step-by-step wizard when called without arguments:

```
hostsctl [rw] > add
hostsctl [rw] > remove
hostsctl [rw] > edit <hostname>     ← wizard if no flags given
hostsctl [rw] > restore
```

---

## How entries are tracked

hostsctl marks every line it writes with an inline tag:

```
10.10.10.5    machine.htb    admin.htb  # HackTheBox  # [hostsctl]
```

Lines without this tag are treated as **system entries** and are never touched by remove or edit. They show up in `list` output labelled `[sys]`.

---

## Backup behaviour

Every destructive operation (`add`, `remove`, `edit`, `restore`) automatically snapshots the current `/etc/hosts` before making any change. You never lose data.

```bash
~/.hostsctl/backups/
├── hosts_20250610_142301
├── hosts_20250610_151807
└── hosts_20250611_093244   ← most recent
```

The 20 most recent backups are kept; older ones are deleted automatically.

---

## Practical examples

### HackTheBox / CTF workflow

```bash
# Box starts
sudo hostsctl add 10.10.11.42 ouija.htb -c "HTB Season 4"

# Discover a vhost
sudo hostsctl edit ouija.htb --ip 10.10.11.42   # same IP, different note
sudo hostsctl add 10.10.11.42 dev.ouija.htb -c "vhost discovered"

# Box retired
sudo hostsctl remove ouija.htb --force
sudo hostsctl remove dev.ouija.htb --force
```

### Lab / dev environment

```bash
# Spin up a whole environment at once
for host in api web db; do
    sudo hostsctl add 192.168.56.10 ${host}.lab.local --force
done

# Tear it all down
sudo hostsctl list managed          # review
sudo hostsctl remove api.lab.local --force
```

### Scripting with exit codes

`hostsctl` returns exit code `0` on success and `1` on error, making it safe to use in scripts:

```bash
sudo hostsctl add 10.0.0.1 target.local && echo "Ready" || echo "Failed"
```

---

## License

MIT — do whatever you want, attribution appreciated.