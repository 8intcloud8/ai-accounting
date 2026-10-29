#!/usr/bin/env python3
import sys
from xero_auth import main

if __name__ == '__main__':
    sys.exit(main(['setup', *sys.argv[1:]]))
