#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys


if os.getuid() != 0:

    print("\nPlease execute this script as sudo.\n")
    sys.exit(1)


def is_file_exists(path: str):

    try:
        with open(path, 'r'):

            pass

    except FileNotFoundError:

        print(f"Err: {path} doesn't exist")
        sys.exit(1)


def host_writing(ip, domain, file_path):
    with open(file_path, "a") as file:
        file.write(f"{ip}\t{domain}\n")


def main():

    try:

        ip = sys.argv[1]
        domain = sys.argv[2]
        file_path = sys.argv[3]

        is_file_exists(file_path)
        host_writing(ip, domain, file_path)

        print(ip, domain, file_path)

    except IndexError:

        print("Usage: script.py <ip> <domain> <file>")
        sys.exit(1)

    except Exception as e:

        print(f"Err: {e}")
        sys.exit(1)


if __name__ == "__main__":
    
    main()
