#!/bin/bash
export LD_PRELOAD="$(pwd)/src/hook/libBotW_AP_Hook.so"
echo "Injecting BotW_AP_Hook.so into Cemu..."

if command -v Cemu &> /dev/null; then
    Cemu "$@"
elif [ -f ~/.local/bin/Cemu ]; then
    ~/.local/bin/Cemu "$@"
elif [ -f /usr/bin/Cemu ]; then
    /usr/bin/Cemu "$@"
else
    echo "Could not find Cemu automatically. Please run Cemu manually with LD_PRELOAD set:"
    echo "LD_PRELOAD=$(pwd)/src/hook/libBotW_AP_Hook.so /path/to/cemu"
fi
