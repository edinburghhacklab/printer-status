#!/usr/bin/env bash
set -euo pipefail

rsync -rlpvP --exclude-from='.rsync-filter' ./ prusa3@prusa3:PrinterStatus/
rsync -rlpvP ./contrib/printer-status.service prusa3@prusa3:.config/systemd/user/printer-status.service

ssh prusa3@prusa3 'systemctl --user daemon-reload && systemctl --user restart printer-status'
