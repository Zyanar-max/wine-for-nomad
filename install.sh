#!/bin/sh
# Wine for Nomad Sculpt - run with sh install.sh   (undo: sh install.sh --uninstall)
cd "$(dirname "$0")" && exec python3 installer.py "$@"
