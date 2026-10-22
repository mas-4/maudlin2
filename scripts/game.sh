#!/bin/bash
# Play a game on the RTX 3080 with the monitor on the motherboard (Oct 22, the person: "that nvidia-prime thing so I can
# turn on and off game mode easily"): gaming mode on for as long as the game runs (app/gaming.py: the worker and
# experiments wait, the hourly runs only scrape), the game drawn on the NVIDIA card through PRIME render offload (what
# nvidia-prime's prime-run does: these three variables), and gaming mode off again when the game ends, unless it was
# already on before.
#
#   scripts/game.sh <the game's command>          e.g. scripts/game.sh godot --path ~/games/mine
#   Steam, a game's launch options:               /home/mas/maudlin-prod/scripts/game.sh %command%
set -u
PROD=/home/mas/maudlin-prod
gaming() { (cd "$PROD" && .venv/bin/python -m app.gaming "$@"); }

[ $# -gt 0 ] || { echo "usage: $0 <the game's command>" >&2; exit 2; }
was_on=0
gaming status >/dev/null 2>&1 && was_on=1
[ "$was_on" = 1 ] || gaming on >/dev/null

__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia __VK_LAYER_NV_optimus=NVIDIA_only "$@"
status=$?

[ "$was_on" = 1 ] || gaming off >/dev/null
exit "$status"
