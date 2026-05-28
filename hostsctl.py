#!/usr/bin/env python3
"""
hostsctl — /etc/hosts manager
Style: same console aesthetic as revshell (ANSI, readline, shlex).
Requires root (or write access to /etc/hosts).
"""

import os
import sys
import re
import shlex
import readline
import shutil
import datetime
from pathlib import Path
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
#  Colours
# ─────────────────────────────────────────────

class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    END    = "\033[0m"

    @staticmethod
    def r(s):    return f"{C.RED}{s}{C.END}"
    @staticmethod
    def g(s):    return f"{C.GREEN}{s}{C.END}"
    @staticmethod
    def y(s):    return f"{C.YELLOW}{s}{C.END}"
    @staticmethod
    def b(s):    return f"{C.BLUE}{s}{C.END}"
    @staticmethod
    def c(s):    return f"{C.CYAN}{s}{C.END}"
    @staticmethod
    def w(s):    return f"{C.WHITE}{s}{C.END}"
    @staticmethod
    def bold(s): return f"{C.BOLD}{s}{C.END}"
    @staticmethod
    def dim(s):  return f"{C.DIM}{s}{C.END}"


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

HOSTS_FILE  = Path("/etc/hosts")
BACKUP_DIR  = Path(os.path.expanduser("~/.hostsctl/backups"))
MAX_BACKUPS = 20          # rotate old backups

SECTION_TAG = "# [hostsctl]"   # marker for entries we manage


# ─────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────

@dataclass
class HostEntry:
    ip:       str
    hostname: str
    aliases:  list[str] = field(default_factory=list)
    comment:  str       = ""
    managed:  bool      = True    # written by hostsctl vs pre-existing

    def names(self) -> list[str]:
        return [self.hostname] + self.aliases

    def render(self) -> str:
        parts = [self.ip, self.hostname] + self.aliases
        line  = "\t".join(parts)
        if self.comment:
            line += f"  # {self.comment}"
        return line


# ─────────────────────────────────────────────
#  Hosts file I/O
# ─────────────────────────────────────────────

def _check_root() -> bool:
    
    if os.getuid() != 0:

        print('\nRun as sudo !\n')
        exit(0);

    else:

        return True 


def backup_hosts() -> Path:
    """Create a timestamped backup of /etc/hosts in BACKUP_DIR."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"hosts_{ts}"
    shutil.copy2(HOSTS_FILE, dest)

    # Rotate: keep only MAX_BACKUPS most recent
    backups = sorted(BACKUP_DIR.glob("hosts_*"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)

    return dest


def parse_hosts() -> tuple[list[str], list[HostEntry]]:
    """
    Parse /etc/hosts.
    Returns (raw_lines, managed_entries).
    raw_lines: every line as-is (for non-destructive rewriting).
    managed_entries: only lines tagged with SECTION_TAG.
    """
    raw: list[str]           = []
    managed: list[HostEntry] = []

    if not HOSTS_FILE.exists():
        return raw, managed

    for line in HOSTS_FILE.read_text().splitlines():
        raw.append(line)
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Check if managed
        is_managed = SECTION_TAG in line
        # Strip inline comments to parse tokens
        code = re.sub(r"#.*$", "", line).strip()
        tokens = code.split()
        if len(tokens) < 2:
            continue
        ip       = tokens[0]
        hostname = tokens[1]
        aliases  = tokens[2:]
        comment_m = re.search(r"#\s*(.+)$", line)
        comment  = ""
        if comment_m:
            c = comment_m.group(1)
            # Strip the section tag from comment text
            c = c.replace(SECTION_TAG.lstrip("# "), "").replace("[hostsctl]", "").strip()
            if c:
                comment = c
        managed.append(HostEntry(ip, hostname, aliases, comment, is_managed))

    return raw, managed


def all_entries() -> list[HostEntry]:
    _, entries = parse_hosts()
    return entries


def write_hosts(new_content: str) -> None:
    HOSTS_FILE.write_text(new_content)


def add_entry(entry: HostEntry) -> str | None:
    """
    Append a managed entry to /etc/hosts.
    Returns error string or None on success.
    """
    if not _check_root():
        return "Permission denied — run as root or with sudo."

    raw, existing = parse_hosts()

    # Duplicate check
    for e in existing:
        if entry.hostname in e.names():
            return f"Hostname '{entry.hostname}' already exists (IP: {e.ip})."

    backup_hosts()

    # Build the new line
    line = entry.render()
    if SECTION_TAG not in line:
        line += f"  {SECTION_TAG}"

    # Add a section header if this is the first managed entry
    has_section = any(SECTION_TAG in l for l in raw)
    if not has_section:
        raw.append("")
        raw.append(f"# ── hostsctl managed entries ──────────────────────")

    raw.append(line)
    write_hosts("\n".join(raw) + "\n")
    return None


def remove_entry(hostname: str) -> str | None:
    """Remove all lines whose canonical hostname or alias matches."""
    if not _check_root():
        return "Permission denied — run as root or with sudo."

    raw, _ = parse_hosts()
    new_lines = []
    removed   = 0

    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        code   = re.sub(r"#.*$", "", line).strip()
        tokens = code.split()
        if len(tokens) >= 2 and hostname in tokens[1:]:
            removed += 1
            continue    # drop this line
        new_lines.append(line)

    if removed == 0:
        return f"No entry found for hostname '{hostname}'."

    backup_hosts()
    write_hosts("\n".join(new_lines) + "\n")
    return None


def edit_entry(hostname: str, new_ip: str | None = None,
               new_hostname: str | None = None,
               new_comment: str | None = None) -> str | None:
    """In-place edit of an entry line."""
    if not _check_root():
        return "Permission denied — run as root or with sudo."

    raw, _ = parse_hosts()
    new_lines = []
    found     = False

    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        code   = re.sub(r"#.*$", "", line).strip()
        tokens = code.split()
        if len(tokens) >= 2 and hostname in tokens[1:]:
            found    = True
            old_ip   = tokens[0]
            old_hn   = tokens[1]
            aliases  = tokens[2:]
            old_comment_m = re.search(r"#\s*(.+)$", line)
            old_comment   = old_comment_m.group(1).strip() if old_comment_m else ""
            # Strip section tag from old comment
            old_comment = old_comment.replace("[hostsctl]", "").replace("hostsctl", "").strip()

            e = HostEntry(
                ip       = new_ip       or old_ip,
                hostname = new_hostname or old_hn,
                aliases  = aliases,
                comment  = new_comment  if new_comment is not None else old_comment,
                managed  = True,
            )
            new_line = e.render()
            if SECTION_TAG not in new_line:
                new_line += f"  {SECTION_TAG}"
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    if not found:
        return f"No entry found for hostname '{hostname}'."

    backup_hosts()
    write_hosts("\n".join(new_lines) + "\n")
    return None


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("hosts_*"), reverse=True)


def restore_backup(path: Path) -> str | None:
    if not _check_root():
        return "Permission denied — run as root or with sudo."
    if not path.exists():
        return f"Backup not found: {path}"
    backup_hosts()   # backup current before restoring
    shutil.copy2(path, HOSTS_FILE)
    return None


# ─────────────────────────────────────────────
#  Display helpers
# ─────────────────────────────────────────────

W = 80   # table width

def hr(char="─", color=C.YELLOW) -> str:
    return f"{C.BOLD}{color}{char * W}{C.END}"


def print_entries_table(entries: list[HostEntry], title: str = "HOSTS") -> None:
    managed_count = sum(1 for e in entries if e.managed)
    other_count   = len(entries) - managed_count

    print(f"\n{hr('═')}")
    t = f" {title} — {len(entries)} entries ({managed_count} managed, {other_count} system) "
    print(f"{C.BOLD}{C.YELLOW}{t.center(W)}{C.END}")
    print(hr("═"))

    # column widths
    ip_w  = max((len(e.ip)       for e in entries), default=15) + 2
    hn_w  = max((len(e.hostname) for e in entries), default=20) + 2
    ip_w  = max(ip_w,  8)
    hn_w  = max(hn_w, 12)

    HDR_IP = "IP"
    HDR_HN = "HOSTNAME"
    HDR_AL = "ALIASES"
    HDR_CM = "COMMENT"

    print(f"  {C.bold(HDR_IP):<{ip_w + len(C.BOLD) + len(C.END)}}"
          f"{C.bold(HDR_HN):<{hn_w + len(C.BOLD) + len(C.END)}}"
          f"{C.bold(HDR_AL):<22}"
          f"{C.bold(HDR_CM)}")
    print(hr("─", C.DIM))

    for e in entries:
        ip_col  = C.g(e.ip) if e.managed else C.dim(e.ip)
        hn_col  = C.c(e.hostname) if e.managed else C.dim(e.hostname)
        al_col  = C.dim(", ".join(e.aliases)) if e.aliases else C.dim("—")
        cm_col  = C.dim(e.comment) if e.comment else ""
        tag_col = f" {C.dim('[sys]')}" if not e.managed else ""

        print(f"  {ip_col:<{ip_w + len(C.GREEN if e.managed else C.DIM) + len(C.END)}}"
              f"{hn_col:<{hn_w + len(C.CYAN if e.managed else C.DIM) + len(C.END)}}"
              f"{al_col:<{22 + len(C.DIM) + len(C.END)}}"
              f"{cm_col}{tag_col}")

    print(hr("═"))
    print()


def print_single_entry(e: HostEntry) -> None:
    print(f"\n{hr('─')}")
    tag = C.g("managed") if e.managed else C.dim("system")
    print(f"  {C.bold(e.hostname)}  {C.dim('→')}  {C.g(e.ip)}  [{tag}]")
    if e.aliases:
        print(f"  {C.dim('Aliases:')}  {', '.join(e.aliases)}")
    if e.comment:
        print(f"  {C.dim('Comment:')}  {e.comment}")
    print(f"  {C.dim('Raw:')}  {e.render()}")
    print(hr("─"))
    print()


def interactive_remove_picker(entries: list[HostEntry]) -> str | None:
    """Display numbered list, return chosen hostname or None."""
    managed = [e for e in entries if e.managed]
    if not managed:
        print(C.r("  [-] No managed entries to remove."))
        return None

    print(f"\n{hr('─')}")
    print(f"  {C.bold('Select an entry to remove:')}")
    print(hr("─", C.DIM))
    for i, e in enumerate(managed, 1):
        print(f"  {C.dim(str(i) + '.'):<{5 + len(C.DIM) + len(C.END)}}"
              f"{C.g(e.ip):<20}{C.c(e.hostname)}")
    print(hr("─"))
    print(f"  {C.dim('Enter number or hostname (empty to cancel):')}")

    try:
        choice = input(f"  {C.BOLD}{C.RED}remove{C.END} {C.BOLD}{C.GREEN}>{C.END} ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if not choice:
        print(C.dim("  Cancelled."))
        return None

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(managed):
            return managed[idx].hostname
        print(C.r(f"  [-] Invalid number: {choice}"))
        return None

    # treat as hostname
    return choice


def interactive_add_wizard() -> HostEntry | None:
    """Step-by-step wizard to build a new HostEntry."""
    print(f"\n{hr('─')}")
    print(f"  {C.bold('Add new host')}  {C.dim('(empty field = cancel)')}")
    print(hr("─", C.DIM))

    def ask(label: str, required: bool = True) -> str | None:
        try:
            val = input(f"  {C.dim(label + ':')} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return None
        if not val and required:
            return None
        return val

    ip = ask("IP address")
    if not ip:
        print(C.dim("  Cancelled."))
        return None
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        print(C.r(f"  [-] Invalid IP address: '{ip}'"))
        return None

    hostname = ask("Hostname")
    if not hostname:
        print(C.dim("  Cancelled."))
        return None

    aliases_raw = ask("Aliases (space-separated, optional)", required=False) or ""
    aliases     = aliases_raw.split() if aliases_raw else []

    comment = ask("Comment (optional)", required=False) or ""

    entry = HostEntry(ip=ip, hostname=hostname, aliases=aliases,
                      comment=comment, managed=True)
    print()
    print(f"  {C.dim('Preview:')}  {C.g(entry.render())}")
    print()

    try:
        confirm = input(f"  {C.dim('Confirm? [Y/n]')} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if confirm in ("", "y", "yes"):
        return entry
    print(C.dim("  Cancelled."))
    return None


def interactive_edit_wizard(hostname: str) -> dict | None:
    """Return dict of fields to update, or None on cancel."""
    entries = all_entries()
    target  = next((e for e in entries if hostname in e.names()), None)
    if not target:
        print(C.r(f"  [-] No entry found for '{hostname}'."))
        return None

    print_single_entry(target)
    print(f"  {C.dim('Leave blank to keep current value.')}")
    print()

    def ask(label: str, current: str) -> str | None:
        try:
            val = input(f"  {C.dim(label)} [{C.g(current)}]{C.dim(':')} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return None
        return val if val else None

    new_ip      = ask("New IP     ", target.ip)
    new_hn      = ask("New name   ", target.hostname)
    new_comment = ask("New comment", target.comment or "—")

    if new_ip is None and new_hn is None and new_comment is None:
        print(C.dim("  Nothing changed."))
        return None

    return {"new_ip": new_ip, "new_hostname": new_hn, "new_comment": new_comment}


def print_backups_table(backups: list[Path]) -> None:
    if not backups:
        print(C.dim(f"  No backups found in {BACKUP_DIR}"))
        return
    print(f"\n{hr('─')}")
    print(f"  {C.bold('BACKUPS')}  {C.dim(str(BACKUP_DIR))}")
    print(hr("─", C.DIM))
    for i, p in enumerate(backups, 1):
        ts_str = p.name.replace("hosts_", "").replace("_", " ")
        sz     = p.stat().st_size
        print(f"  {C.dim(str(i) + '.'):<{5 + len(C.DIM) + len(C.END)}}"
              f"{C.g(p.name):<38}{C.dim(ts_str + '   ' + str(sz) + ' B')}")
    print(hr("─"))
    print()


# ─────────────────────────────────────────────
#  Banner / Help
# ─────────────────────────────────────────────

BANNER = f"""
{C.BOLD}{C.RED}
  ██╗  ██╗ ██████╗ ███████╗████████╗███████╗ ██████╗████████╗██╗
  ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██║
  ███████║██║   ██║███████╗   ██║   ███████╗██║        ██║   ██║
  ██╔══██║██║   ██║╚════██║   ██║   ╚════██║██║        ██║   ██║
  ██║  ██║╚██████╔╝███████║   ██║   ███████║╚██████╗   ██║   ███████╗
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝   ╚═╝   ╚══════╝
{C.END}{C.DIM}
  /etc/hosts manager console{C.END}
{C.END}{C.DIM}  Author: {C.BOLD}{C.RED}@ZetaOrioniss{C.END}
{C.END}{C.DIM}  Version: {C.BOLD}{C.RED}v1.0{C.END}
{C.DIM}
  Backups stored in: {C.END}{C.BOLD}{str(BACKUP_DIR)}{C.END}
{C.DIM}  Type {C.END}{C.BOLD}help{C.END}{C.DIM} to list available commands.{C.END}
"""

HELP = f"""
{C.BOLD}{C.YELLOW}
╔══════════════════════════════════════════════════════════════╗
║                          COMMANDS                            ║
╚══════════════════════════════════════════════════════════════╝{C.END}

  {C.bold('Listing')}
  {C.g('list')}  /  {C.g('ls')}                  Show all entries (managed + system)
  {C.g('list managed')}               Show only hostsctl-managed entries
  {C.g('list system')}                Show only pre-existing system entries
  {C.g('search <term>')}              Search by IP, hostname, or alias
  {C.g('show <hostname>')}            Display details for one entry

  {C.bold('Adding')}
  {C.g('add <ip> <hostname> [alias…] [--comment "…"]')}
                              Add an entry directly
  {C.g('add')}                         Interactive wizard (step-by-step)

  {C.bold('Removing')}
  {C.g('remove <hostname>')}           Remove entry by hostname/alias
  {C.g('remove')}                       Interactive picker

  {C.bold('Editing')}
  {C.g('edit <hostname>')}             Interactive edit wizard
  {C.g('edit <hostname> --ip <ip>')}   Change only the IP
  {C.g('edit <hostname> --name <n>')}  Rename the hostname
  {C.g('edit <hostname> --comment "…"')} Update comment

  {C.bold('Backups')}
  {C.g('backup')}                      Create a manual backup now
  {C.g('backups')}  /  {C.g('backup list')}      List all saved backups
  {C.g('restore')}                      Interactive restore picker
  {C.g('restore <n>')}                 Restore backup by number

  {C.bold('Other')}
  {C.g('clear')}                       Clear the screen
  {C.g('help')}                        Show this help
  {C.g('exit')}  /  {C.g('quit')}               Exit
"""


# ─────────────────────────────────────────────
#  Tab completion
# ─────────────────────────────────────────────

COMMANDS = [
    "list", "ls", "search", "show",
    "add", "remove", "edit",
    "backup", "backups", "restore",
    "clear", "help", "exit", "quit",
]
LIST_OPTS   = ["managed", "system"]
BACKUP_OPTS = ["list"]


def _hostnames() -> list[str]:
    try:
        return [e.hostname for e in all_entries()]
    except Exception:
        return []


def completer(text: str, state: int):
    line   = readline.get_line_buffer().lstrip()
    parts  = line.split()
    nparts = len(parts)

    if nparts == 0 or (nparts == 1 and not line.endswith(" ")):
        opts = [c for c in COMMANDS if c.startswith(text)]
    elif parts[0] in ("list", "ls") and nparts <= 2:
        opts = [o for o in LIST_OPTS if o.startswith(text)]
    elif parts[0] in ("show", "remove", "edit") and nparts <= 2:
        opts = [h for h in _hostnames() if h.startswith(text)]
    elif parts[0] == "edit" and nparts >= 3:
        opts = [o for o in ("--ip", "--name", "--comment") if o.startswith(text)]
    elif parts[0] == "backup" and nparts <= 2:
        opts = [o for o in BACKUP_OPTS if o.startswith(text)]
    else:
        opts = []

    return opts[state] if state < len(opts) else None


readline.set_completer(completer)
readline.parse_and_bind("tab: complete")


# ─────────────────────────────────────────────
#  Prompt
# ─────────────────────────────────────────────

def prompt() -> str:
    rw = C.g("rw") if _check_root() else C.r("ro")
    return (f"{C.BOLD}{C.RED}hostsctl{C.END} "
            f"{C.dim('[' + rw + C.dim(']'))} "
            f"{C.BOLD}{C.GREEN}>{C.END} ")


# ─────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────

def run_console() -> None:
    print(BANNER)

    if not _check_root():
        print(C.y("  [!] /etc/hosts is read-only for this user."))
        print(f"  {C.dim('Run with sudo for write access. Listing still works.')}\n")

    while True:
        try:
            raw = input(prompt()).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.dim('Goodbye.')}\n")
            break

        if not raw:
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as e:
            print(C.r(f"  [-] Parse error: {e}"))
            continue

        cmd  = parts[0].lower()
        args = parts[1:]

        # ── exit ──────────────────────────────────────────────────────────
        if cmd in ("exit", "quit"):
            print(f"\n{C.dim('Goodbye.')}\n")
            break

        # ── help ──────────────────────────────────────────────────────────
        elif cmd == "help":
            print(HELP)

        # ── clear ─────────────────────────────────────────────────────────
        elif cmd == "clear":
            print("\033[2J\033[H", end="")
            print(BANNER)

        # ── list / ls ─────────────────────────────────────────────────────
        elif cmd in ("list", "ls"):
            sub     = args[0].lower() if args else ""
            entries = all_entries()
            if sub == "managed":
                entries = [e for e in entries if e.managed]
                print_entries_table(entries, "MANAGED ENTRIES")
            elif sub == "system":
                entries = [e for e in entries if not e.managed]
                print_entries_table(entries, "SYSTEM ENTRIES")
            else:
                print_entries_table(entries, "ALL ENTRIES")

        # ── search ────────────────────────────────────────────────────────
        elif cmd == "search":
            if not args:
                print(C.r("  Usage: search <term>"))
            else:
                term    = args[0].lower()
                entries = all_entries()
                found   = [e for e in entries
                           if term in e.ip.lower()
                           or any(term in n.lower() for n in e.names())]
                if found:
                    print_entries_table(found, f"SEARCH '{args[0]}'")
                else:
                    print(C.dim(f"  No entries matching '{args[0]}'."))

        # ── show ──────────────────────────────────────────────────────────
        elif cmd == "show":
            if not args:
                print(C.r("  Usage: show <hostname>"))
            else:
                hostname = args[0]
                entries  = all_entries()
                target   = next((e for e in entries if hostname in e.names()), None)
                if target:
                    print_single_entry(target)
                else:
                    print(C.r(f"  [-] No entry found for '{hostname}'."))

        # ── add ───────────────────────────────────────────────────────────
        elif cmd == "add":
            if not args:
                # wizard
                entry = interactive_add_wizard()
                if entry:
                    err = add_entry(entry)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Added: {C.g(entry.hostname)} → {entry.ip}")
            else:
                # inline: add <ip> <hostname> [aliases…] [--comment "…"]
                comment = ""
                clean_args = []
                i = 0
                while i < len(args):
                    if args[i] == "--comment" and i + 1 < len(args):
                        comment = args[i + 1]
                        i += 2
                    else:
                        clean_args.append(args[i])
                        i += 1

                if len(clean_args) < 2:
                    print(C.r("  Usage: add <ip> <hostname> [aliases…] [--comment \"…\"]"))
                else:
                    ip       = clean_args[0]
                    hostname = clean_args[1]
                    aliases  = clean_args[2:]

                    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                        print(C.r(f"  [-] Invalid IP address: '{ip}'"))
                    else:
                        entry = HostEntry(ip, hostname, aliases, comment, managed=True)
                        err   = add_entry(entry)
                        if err:
                            print(C.r(f"  [-] {err}"))
                        else:
                            print(f"  {C.g('✔')}  Added: {C.g(hostname)} → {ip}")

        # ── remove ────────────────────────────────────────────────────────
        elif cmd == "remove":
            if not args:
                # interactive picker
                entries  = all_entries()
                hostname = interactive_remove_picker(entries)
                if hostname:
                    err = remove_entry(hostname)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Removed: {C.g(hostname)}")
            else:
                hostname = args[0]
                err      = remove_entry(hostname)
                if err:
                    print(C.r(f"  [-] {err}"))
                else:
                    print(f"  {C.g('✔')}  Removed: {C.g(hostname)}")

        # ── edit ──────────────────────────────────────────────────────────
        elif cmd == "edit":
            if not args:
                print(C.r("  Usage: edit <hostname> [--ip <ip>] [--name <name>] [--comment \"…\"]"))
            else:
                hostname    = args[0]
                rest        = args[1:]
                new_ip      = None
                new_name    = None
                new_comment = None

                # Parse inline flags
                i = 0
                has_flags = False
                while i < len(rest):
                    if rest[i] == "--ip" and i + 1 < len(rest):
                        new_ip    = rest[i + 1]; has_flags = True; i += 2
                    elif rest[i] == "--name" and i + 1 < len(rest):
                        new_name  = rest[i + 1]; has_flags = True; i += 2
                    elif rest[i] == "--comment" and i + 1 < len(rest):
                        new_comment = rest[i + 1]; has_flags = True; i += 2
                    else:
                        i += 1

                if not has_flags:
                    # wizard
                    changes = interactive_edit_wizard(hostname)
                    if changes:
                        err = edit_entry(hostname, **changes)
                        if err:
                            print(C.r(f"  [-] {err}"))
                        else:
                            print(f"  {C.g('✔')}  Updated: {C.g(hostname)}")
                else:
                    err = edit_entry(hostname, new_ip=new_ip,
                                     new_hostname=new_name, new_comment=new_comment)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Updated: {C.g(hostname)}")

        # ── backup ────────────────────────────────────────────────────────
        elif cmd == "backup":
            sub = args[0].lower() if args else ""
            if sub == "list":
                print_backups_table(list_backups())
            else:
                dest = backup_hosts()
                print(f"  {C.g('✔')}  Backup saved: {C.g(str(dest))}")

        # ── backups ───────────────────────────────────────────────────────
        elif cmd == "backups":
            print_backups_table(list_backups())

        # ── restore ───────────────────────────────────────────────────────
        elif cmd == "restore":
            backups = list_backups()
            if not backups:
                print(C.dim("  No backups available."))
            elif args and args[0].isdigit():
                idx = int(args[0]) - 1
                if 0 <= idx < len(backups):
                    chosen = backups[idx]
                    err    = restore_backup(chosen)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Restored: {C.g(chosen.name)}")
                else:
                    print(C.r(f"  [-] Invalid backup number: {args[0]}"))
            else:
                # interactive picker
                print_backups_table(backups)
                print(f"  {C.dim('Enter backup number to restore (empty to cancel):')}")
                try:
                    choice = input(f"  {C.BOLD}{C.RED}restore{C.END} {C.BOLD}{C.GREEN}>{C.END} ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    continue

                if not choice:
                    print(C.dim("  Cancelled."))
                    continue

                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(backups):
                        chosen = backups[idx]
                        # Confirm
                        print(f"\n  {C.y('[!] This will overwrite /etc/hosts with:')} {C.g(chosen.name)}")
                        try:
                            confirm = input(f"  {C.dim('Confirm? [y/N]')} ").strip().lower()
                        except (KeyboardInterrupt, EOFError):
                            print()
                            continue
                        if confirm in ("y", "yes"):
                            err = restore_backup(chosen)
                            if err:
                                print(C.r(f"  [-] {err}"))
                            else:
                                print(f"  {C.g('✔')}  Restored: {C.g(chosen.name)}")
                        else:
                            print(C.dim("  Cancelled."))
                    else:
                        print(C.r(f"  [-] Invalid number: {choice}"))
                else:
                    print(C.r(f"  [-] Please enter a number."))

        # ── unknown ───────────────────────────────────────────────────────
        else:
            print(C.r(f"  [-] Unknown command: '{cmd}'"))
            print(f"  {C.dim('Type')} help {C.dim('for available commands.')}")


if __name__ == "__main__":
    run_console()