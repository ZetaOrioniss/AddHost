#!/usr/bin/env python3
"""
hostsctl — /etc/hosts manager
Style: same console aesthetic as revshell (ANSI, readline, shlex).
Requires root (or write access to /etc/hosts).

CLI USAGE (non-interactive):
  hostsctl list [managed|system]
  hostsctl add <ip> <hostname> [aliases…] [-c "comment"]
  hostsctl remove <hostname>
  hostsctl edit <hostname> [--ip <ip>] [--name <n>] [-c "comment"]
  hostsctl search <term>
  hostsctl show <hostname>
  hostsctl backup [list]
  hostsctl restore <n>
"""

import os
import sys
import re
import shlex
import readline
import shutil
import datetime
import argparse
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
MAX_BACKUPS = 20

SECTION_TAG = "# [hostsctl]"


# ─────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────

@dataclass
class HostEntry:
    ip:       str
    hostname: str
    aliases:  list[str] = field(default_factory=list)
    comment:  str       = ""
    managed:  bool      = True

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
        exit(0)
    else:
        return True


def backup_hosts() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"hosts_{ts}"
    shutil.copy2(HOSTS_FILE, dest)
    backups = sorted(BACKUP_DIR.glob("hosts_*"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)
    return dest


def parse_hosts() -> tuple[list[str], list[HostEntry]]:
    raw: list[str]           = []
    managed: list[HostEntry] = []

    if not HOSTS_FILE.exists():
        return raw, managed

    for line in HOSTS_FILE.read_text().splitlines():
        raw.append(line)
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        is_managed = SECTION_TAG in line
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
    if not _check_root():
        return "Permission denied — run as root or with sudo."

    raw, existing = parse_hosts()

    for e in existing:
        if entry.hostname in e.names():
            return f"Hostname '{entry.hostname}' already exists (IP: {e.ip})."

    backup_hosts()

    line = entry.render()
    if SECTION_TAG not in line:
        line += f"  {SECTION_TAG}"

    has_section = any(SECTION_TAG in l for l in raw)
    if not has_section:
        raw.append("")
        raw.append(f"# ── hostsctl managed entries ──────────────────────")

    raw.append(line)
    write_hosts("\n".join(raw) + "\n")
    return None


def remove_entry(hostname: str) -> str | None:
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
            continue
        new_lines.append(line)

    if removed == 0:
        return f"No entry found for hostname '{hostname}'."

    backup_hosts()
    write_hosts("\n".join(new_lines) + "\n")
    return None


def edit_entry(hostname: str, new_ip: str | None = None,
               new_hostname: str | None = None,
               new_comment: str | None = None,
               add_aliases: list[str] | None = None,
               remove_aliases: list[str] | None = None) -> str | None:
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

            if remove_aliases:
                aliases = [a for a in aliases if a not in remove_aliases]
            if add_aliases:
                for a in add_aliases:
                    if a not in aliases and a != old_hn:
                        aliases.append(a)

            old_comment_m = re.search(r"#\s*(.+)$", line)
            old_comment   = old_comment_m.group(1).strip() if old_comment_m else ""
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
    backup_hosts()
    shutil.copy2(path, HOSTS_FILE)
    return None


# ─────────────────────────────────────────────
#  Display helpers
# ─────────────────────────────────────────────

W = 80

def hr(char="─", color=C.YELLOW) -> str:
    return f"{C.BOLD}{color}{char * W}{C.END}"


def print_entries_table(entries: list[HostEntry], title: str = "HOSTS") -> None:
    managed_count = sum(1 for e in entries if e.managed)
    other_count   = len(entries) - managed_count
    print("\n")
    t = f" {title} — {len(entries)} entries ({managed_count} managed, {other_count} system) "
    print(f"{C.WHITE}{t.center(W)}{C.END}")
    print("\n")

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

    print(hr("─", C.DIM))
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


def interactive_remove_picker(entries: list[HostEntry]) -> list[str] | None:
    managed = [e for e in entries if e.managed]
    if not managed:
        print(C.r("  [-] No managed entries to remove."))
        return None

    print(f"\n{hr('─')}")
    print(f"  {C.bold('Select one or more entries to remove:')}")
    print(hr("─", C.DIM))
    for i, e in enumerate(managed, 1):
        print(f"  {C.dim(str(i) + '.'):<{5 + len(C.DIM) + len(C.END)}}"
              f"{C.g(e.ip):<20}{C.c(e.hostname)}")
    print(hr("─"))
    print(f"  {C.dim('Enter number(s) (e.g. 1,3,5 or 2-4), hostname(s), \"all\", or empty to cancel:')}")

    try:
        choice = input(f"  {C.BOLD}{C.RED}remove{C.END} {C.BOLD}{C.GREEN}>{C.END} ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None

    if not choice:
        print(C.dim("  Cancelled."))
        return None

    if choice.lower() == "all":
        return [e.hostname for e in managed]

    hostnames: list[str] = []
    for token in re.split(r"[,\s]+", choice):
        if not token:
            continue
        if re.match(r"^\d+-\d+$", token):
            start, end = (int(n) for n in token.split("-"))
            for idx in range(start, end + 1):
                if 1 <= idx <= len(managed):
                    hostnames.append(managed[idx - 1].hostname)
                else:
                    print(C.r(f"  [-] Invalid number: {idx}"))
        elif token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(managed):
                hostnames.append(managed[idx - 1].hostname)
            else:
                print(C.r(f"  [-] Invalid number: {token}"))
        else:
            hostnames.append(token)

    return hostnames or None


def interactive_add_wizard() -> HostEntry | None:
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

    new_ip      = ask("New IP        ", target.ip)
    new_hn      = ask("New name      ", target.hostname)
    new_comment = ask("New comment   ", target.comment or "—")

    current_aliases = ", ".join(target.aliases) if target.aliases else "—"
    add_raw    = ask("Add aliases   ", f"none, current: {current_aliases}")
    remove_raw = ask("Remove aliases", "none")

    add_aliases    = add_raw.split()    if add_raw    else None
    remove_aliases = remove_raw.split() if remove_raw else None

    if (new_ip is None and new_hn is None and new_comment is None
            and not add_aliases and not remove_aliases):
        print(C.dim("  Nothing changed."))
        return None

    return {
        "new_ip": new_ip, "new_hostname": new_hn, "new_comment": new_comment,
        "add_aliases": add_aliases, "remove_aliases": remove_aliases,
    }


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
{C.WHITE}
╔══════════════════════════════════════════════════════════════╗
║                          HOSTsCTL                            ║
╚══════════════════════════════════════════════════════════════╝
{C.END}{C.DIM}
  /etc/hosts manager console{C.END}
{C.END}{C.DIM}  Author: {C.BOLD}{C.RED}@ZetaOrioniss{C.END}
{C.END}{C.DIM}  Version: {C.BOLD}{C.RED}v1.1{C.END}
{C.DIM}
  Backups stored in: {C.END}{C.BOLD}{str(BACKUP_DIR)}{C.END}
{C.DIM}  Type {C.END}{C.BOLD}help{C.END}{C.DIM} to list available commands.{C.END}
"""

HELP = f"""
{C.BOLD}{C.WHITE}
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
  {C.g('remove <h1> <h2> …')}          Remove several entries at once
  {C.g('remove')}                       Interactive picker (supports 1,3,5 or "all")

  {C.bold('Editing')}
  {C.g('edit <hostname>')}             Interactive edit wizard
  {C.g('edit <hostname> --ip <ip>')}   Change only the IP
  {C.g('edit <hostname> --name <n>')}  Rename the hostname
  {C.g('edit <hostname> --comment "…"')} Update comment
  {C.g('edit <hostname> --add-alias <a1> [a2…]')}    Add one or more aliases
  {C.g('edit <hostname> --remove-alias <a1> [a2…]')} Remove one or more aliases

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

CLI_HELP_EPILOG = f"""
{C.BOLD}Examples:{C.END}
  # List all entries
  sudo hostsctl list
  sudo hostsctl list managed
  sudo hostsctl list system

  # Add entries
  sudo hostsctl add 10.10.10.5 machine.htb
  sudo hostsctl add 10.10.10.5 machine.htb admin.machine.htb -c "HackTheBox box"
  sudo hostsctl add 192.168.1.100 dev.local api.dev.local web.dev.local -c "dev env"

  # Remove
  sudo hostsctl remove machine.htb
  sudo hostsctl remove machine.htb --force        # no confirmation prompt
  sudo hostsctl remove machine.htb old.htb stale.htb    # remove several at once
  sudo hostsctl remove machine.htb old.htb --force

  # Edit
  sudo hostsctl edit machine.htb --ip 10.10.10.99
  sudo hostsctl edit machine.htb --name newbox.htb
  sudo hostsctl edit machine.htb -c "retired box"
  sudo hostsctl edit machine.htb --ip 10.0.0.1 --name other.htb -c "updated"
  sudo hostsctl edit machine.htb --add-alias admin.machine.htb dev.machine.htb
  sudo hostsctl edit machine.htb --remove-alias admin.machine.htb

  # Search & show
  sudo hostsctl search 10.10.10
  sudo hostsctl show machine.htb

  # Backups
  sudo hostsctl backup
  sudo hostsctl backup list
  sudo hostsctl restore 1               # restore latest backup by index
  sudo hostsctl restore --list          # print backup list and exit

  # Launch interactive console (no subcommand)
  sudo hostsctl
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
        opts = [o for o in ("--ip", "--name", "--comment",
                             "--add-alias", "--remove-alias") if o.startswith(text)]
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
#  CLI argument parser
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hostsctl",
        description=f"{C.BOLD}{C.WHITE}hostsctl{C.END} — /etc/hosts manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_HELP_EPILOG,
        add_help=True,
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── list ──────────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", aliases=["ls"],
        help="List entries  [managed|system|all]")
    p_list.add_argument("filter", nargs="?", choices=["managed", "system", "all"],
        default="all", metavar="managed|system|all",
        help="Filter subset (default: all)")

    # ── search ────────────────────────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search entries by IP, hostname, or alias")
    p_search.add_argument("term", help="Search term")

    # ── show ──────────────────────────────────────────────────────────────
    p_show = sub.add_parser("show", help="Show details for one entry")
    p_show.add_argument("hostname", help="Hostname or alias to display")

    # ── add ───────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Add a new host entry")
    p_add.add_argument("ip",       help="IPv4 address  e.g. 10.10.10.5")
    p_add.add_argument("hostname", help="Canonical hostname  e.g. machine.htb")
    p_add.add_argument("aliases",  nargs="*", metavar="alias",
        help="Optional extra names/aliases")
    p_add.add_argument("-c", "--comment", default="",
        metavar="TEXT", help="Inline comment")

    # ── remove ────────────────────────────────────────────────────────────
    p_rm = sub.add_parser("remove", aliases=["rm", "del"],
        help="Remove one or more entries by hostname/alias")
    p_rm.add_argument("hostnames", nargs="+", metavar="hostname",
        help="One or more hostnames/aliases to remove")
    p_rm.add_argument("-f", "--force", action="store_true",
        help="Skip confirmation prompt")

    # ── edit ──────────────────────────────────────────────────────────────
    p_edit = sub.add_parser("edit", help="Edit an existing entry in-place")
    p_edit.add_argument("hostname", help="Hostname or alias to edit")
    p_edit.add_argument("--ip",   dest="new_ip",   default=None, metavar="ADDR",
        help="New IP address")
    p_edit.add_argument("--name", dest="new_name", default=None, metavar="NAME",
        help="New canonical hostname")
    p_edit.add_argument("-c", "--comment", dest="new_comment", default=None,
        metavar="TEXT", help="New comment (use '' to clear)")
    p_edit.add_argument("--add-alias", dest="add_aliases", nargs="+", default=None,
        metavar="ALIAS", help="Add one or more aliases")
    p_edit.add_argument("--remove-alias", dest="remove_aliases", nargs="+", default=None,
        metavar="ALIAS", help="Remove one or more aliases")

    # ── backup ────────────────────────────────────────────────────────────
    p_bk = sub.add_parser("backup", help="Create a backup or list existing ones")
    p_bk.add_argument("action", nargs="?", choices=["list"],
        metavar="list", help="'list' to show saved backups")

    # ── backups (alias) ───────────────────────────────────────────────────
    sub.add_parser("backups", help="List all saved backups (alias for 'backup list')")

    # ── restore ───────────────────────────────────────────────────────────
    p_rst = sub.add_parser("restore", help="Restore a backup")
    p_rst.add_argument("index", nargs="?", type=int, default=None,
        metavar="N", help="Backup number (from 'backup list'); omit for interactive")
    p_rst.add_argument("-l", "--list", dest="show_list", action="store_true",
        help="Print backup list and exit")
    p_rst.add_argument("-f", "--force", action="store_true",
        help="Skip confirmation prompt")

    return parser


# ─────────────────────────────────────────────
#  CLI dispatch  (non-interactive)
# ─────────────────────────────────────────────

def run_cli(args: argparse.Namespace) -> int:
    """Execute a single CLI command. Returns exit code."""

    cmd = args.command

    # normalise aliases
    if cmd in ("ls",):        cmd = "list"
    if cmd in ("rm", "del"):  cmd = "remove"
    if cmd == "backups":      cmd = "backup"; args.action = "list"

    # ── list ──────────────────────────────────────────────────────────────
    if cmd == "list":
        entries = all_entries()
        f = getattr(args, "filter", "all")
        if f == "managed":
            entries = [e for e in entries if e.managed]
            print_entries_table(entries, "MANAGED ENTRIES")
        elif f == "system":
            entries = [e for e in entries if not e.managed]
            print_entries_table(entries, "SYSTEM ENTRIES")
        else:
            print_entries_table(entries, "ALL ENTRIES")

    # ── search ────────────────────────────────────────────────────────────
    elif cmd == "search":
        term    = args.term.lower()
        entries = all_entries()
        found   = [e for e in entries
                   if term in e.ip.lower()
                   or any(term in n.lower() for n in e.names())]
        if found:
            print_entries_table(found, f"SEARCH '{args.term}'")
        else:
            print(C.dim(f"  No entries matching '{args.term}'."))

    # ── show ──────────────────────────────────────────────────────────────
    elif cmd == "show":
        entries = all_entries()
        target  = next((e for e in entries if args.hostname in e.names()), None)
        if target:
            print_single_entry(target)
        else:
            print(C.r(f"  [-] No entry found for '{args.hostname}'."))
            return 1

    # ── add ───────────────────────────────────────────────────────────────
    elif cmd == "add":
        ip = args.ip
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
            print(C.r(f"  [-] Invalid IP address: '{ip}'"))
            return 1
        entry = HostEntry(ip=ip, hostname=args.hostname,
                          aliases=args.aliases, comment=args.comment, managed=True)
        err = add_entry(entry)
        if err:
            print(C.r(f"  [-] {err}"))
            return 1
        print(f"  {C.g('✔')}  Added: {C.g(args.hostname)} → {ip}")

    # ── remove ────────────────────────────────────────────────────────────
    elif cmd == "remove":
        hostnames = args.hostnames
        if not getattr(args, "force", False):
            label = hostnames[0] if len(hostnames) == 1 else f"{len(hostnames)} entries"
            try:
                confirm = input(
                    f"  {C.y('[!] Remove')} {C.bold(label)}{C.y('?')} "
                    f"{C.dim('[y/N]')} "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return 0
            if confirm not in ("y", "yes"):
                print(C.dim("  Cancelled."))
                return 0

        ok_count = 0
        exit_code = 0
        for hostname in hostnames:
            err = remove_entry(hostname)
            if err:
                print(C.r(f"  [-] {err}"))
                exit_code = 1
            else:
                print(f"  {C.g('✔')}  Removed: {C.g(hostname)}")
                ok_count += 1
        if len(hostnames) > 1:
            print(f"  {C.dim(f'{ok_count}/{len(hostnames)} entries removed.')}")
        return exit_code

    # ── edit ──────────────────────────────────────────────────────────────
    elif cmd == "edit":
        add_aliases    = getattr(args, "add_aliases", None)
        remove_aliases = getattr(args, "remove_aliases", None)
        if (args.new_ip is None and args.new_name is None and args.new_comment is None
                and not add_aliases and not remove_aliases):
            # no flags → wizard
            changes = interactive_edit_wizard(args.hostname)
            if changes:
                err = edit_entry(args.hostname, **changes)
                if err:
                    print(C.r(f"  [-] {err}"))
                    return 1
                print(f"  {C.g('✔')}  Updated: {C.g(args.hostname)}")
        else:
            err = edit_entry(args.hostname,
                             new_ip=args.new_ip,
                             new_hostname=args.new_name,
                             new_comment=args.new_comment,
                             add_aliases=add_aliases,
                             remove_aliases=remove_aliases)
            if err:
                print(C.r(f"  [-] {err}"))
                return 1
            print(f"  {C.g('✔')}  Updated: {C.g(args.hostname)}")

    # ── backup ────────────────────────────────────────────────────────────
    elif cmd == "backup":
        action = getattr(args, "action", None)
        if action == "list":
            print_backups_table(list_backups())
        else:
            dest = backup_hosts()
            print(f"  {C.g('✔')}  Backup saved: {C.g(str(dest))}")

    # ── restore ───────────────────────────────────────────────────────────
    elif cmd == "restore":
        backups = list_backups()
        if not backups:
            print(C.dim("  No backups available."))
            return 1

        if getattr(args, "show_list", False):
            print_backups_table(backups)
            return 0

        if args.index is not None:
            idx = args.index - 1
            if not (0 <= idx < len(backups)):
                print(C.r(f"  [-] Invalid backup number: {args.index}"))
                return 1
            chosen = backups[idx]
            if not getattr(args, "force", False):
                print(f"\n  {C.y('[!] This will overwrite /etc/hosts with:')} {C.g(chosen.name)}")
                try:
                    confirm = input(f"  {C.dim('Confirm? [y/N]')} ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print()
                    return 0
                if confirm not in ("y", "yes"):
                    print(C.dim("  Cancelled."))
                    return 0
            err = restore_backup(chosen)
            if err:
                print(C.r(f"  [-] {err}"))
                return 1
            print(f"  {C.g('✔')}  Restored: {C.g(chosen.name)}")
        else:
            # interactive restore inside CLI mode
            print_backups_table(backups)
            print(f"  {C.dim('Enter backup number to restore (empty to cancel):')}")
            try:
                choice = input(
                    f"  {C.BOLD}{C.RED}restore{C.END} {C.BOLD}{C.GREEN}>{C.END} "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return 0

            if not choice or not choice.isdigit():
                print(C.dim("  Cancelled."))
                return 0

            idx = int(choice) - 1
            if not (0 <= idx < len(backups)):
                print(C.r(f"  [-] Invalid number: {choice}"))
                return 1
            chosen = backups[idx]
            print(f"\n  {C.y('[!] This will overwrite /etc/hosts with:')} {C.g(chosen.name)}")
            try:
                confirm = input(f"  {C.dim('Confirm? [y/N]')} ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return 0
            if confirm in ("y", "yes"):
                err = restore_backup(chosen)
                if err:
                    print(C.r(f"  [-] {err}"))
                    return 1
                print(f"  {C.g('✔')}  Restored: {C.g(chosen.name)}")
            else:
                print(C.dim("  Cancelled."))

    return 0


# ─────────────────────────────────────────────
#  Interactive console
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
                entry = interactive_add_wizard()
                if entry:
                    err = add_entry(entry)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Added: {C.g(entry.hostname)} → {entry.ip}")
            else:
                comment = ""
                clean_args = []
                i = 0
                while i < len(args):
                    if args[i] in ("--comment", "-c") and i + 1 < len(args):
                        comment = args[i + 1]
                        i += 2
                    else:
                        clean_args.append(args[i])
                        i += 1

                if len(clean_args) < 2:
                    print(C.r("  Usage: add <ip> <hostname> [aliases…] [-c \"…\"]"))
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
                entries    = all_entries()
                hostnames  = interactive_remove_picker(entries)
                if hostnames:
                    ok_count = 0
                    for hostname in hostnames:
                        err = remove_entry(hostname)
                        if err:
                            print(C.r(f"  [-] {err}"))
                        else:
                            print(f"  {C.g('✔')}  Removed: {C.g(hostname)}")
                            ok_count += 1
                    if len(hostnames) > 1:
                        print(f"  {C.dim(f'{ok_count}/{len(hostnames)} entries removed.')}")
            else:
                hostnames = args
                ok_count  = 0
                for hostname in hostnames:
                    err = remove_entry(hostname)
                    if err:
                        print(C.r(f"  [-] {err}"))
                    else:
                        print(f"  {C.g('✔')}  Removed: {C.g(hostname)}")
                        ok_count += 1
                if len(hostnames) > 1:
                    print(f"  {C.dim(f'{ok_count}/{len(hostnames)} entries removed.')}")

        # ── edit ──────────────────────────────────────────────────────────
        elif cmd == "edit":
            if not args:
                print(C.r("  Usage: edit <hostname> [--ip <ip>] [--name <name>] "
                           "[-c \"…\"] [--add-alias <a…>] [--remove-alias <a…>]"))
            else:
                hostname       = args[0]
                rest           = args[1:]
                new_ip         = None
                new_name       = None
                new_comment    = None
                add_aliases    = []
                remove_aliases = []

                i = 0
                has_flags = False
                while i < len(rest):
                    if rest[i] == "--ip" and i + 1 < len(rest):
                        new_ip = rest[i + 1]; has_flags = True; i += 2
                    elif rest[i] == "--name" and i + 1 < len(rest):
                        new_name = rest[i + 1]; has_flags = True; i += 2
                    elif rest[i] in ("--comment", "-c") and i + 1 < len(rest):
                        new_comment = rest[i + 1]; has_flags = True; i += 2
                    elif rest[i] == "--add-alias":
                        has_flags = True
                        i += 1
                        while i < len(rest) and not rest[i].startswith("--"):
                            add_aliases.append(rest[i])
                            i += 1
                    elif rest[i] == "--remove-alias":
                        has_flags = True
                        i += 1
                        while i < len(rest) and not rest[i].startswith("--"):
                            remove_aliases.append(rest[i])
                            i += 1
                    else:
                        i += 1

                if not has_flags:
                    changes = interactive_edit_wizard(hostname)
                    if changes:
                        err = edit_entry(hostname, **changes)
                        if err:
                            print(C.r(f"  [-] {err}"))
                        else:
                            print(f"  {C.g('✔')}  Updated: {C.g(hostname)}")
                else:
                    err = edit_entry(hostname, new_ip=new_ip,
                                     new_hostname=new_name, new_comment=new_comment,
                                     add_aliases=add_aliases or None,
                                     remove_aliases=remove_aliases or None)
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


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # If called with no arguments → interactive console
    if len(sys.argv) == 1:
        run_console()
        sys.exit(0)

    parser = build_parser()
    args   = parser.parse_args()

    if args.command is None:
        # e.g. `hostsctl --help` already handled by argparse
        parser.print_help()
        sys.exit(0)

    sys.exit(run_cli(args))
