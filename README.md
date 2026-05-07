# HostAdd

A simple Python script to add IP-to-domain mappings into a hosts-style file (e.g. `/etc/hosts`).

## ⚙️ Features

- Checks for root privileges before execution
- Verifies that the target file exists
- Appends IP → domain mappings safely
- Simple CLI usage

---

## 🚀 Usage

```bash
sudo python3 host_add.py <ip> <domain> <file>
