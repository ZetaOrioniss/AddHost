# HostAdd

I was tired of manually adding hosts during CTFs, so I built this simple Python script to automate the process. It adds IP-to-domain mappings into a hosts-style file (e.g. /etc/hosts) quickly and easily.

## ⚙️ Features

- Checks for root privileges before execution
- Verifies that the target file exists
- Appends IP → domain mappings safely
- Simple CLI usage

---

## 🚀 Usage

```bash
sudo python3 host_add.py <ip> <domain> <file>
