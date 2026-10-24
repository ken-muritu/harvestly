#!/bin/sh
# One source of truth: copy the engine, its demo vectors and the shared bot core into lib/ (run before deploy).
# test_webhook.py asserts these copies are byte-identical to the sources.
set -e
cd "$(dirname "$0")"
cp ../engine/harvestly_engine.py ../engine/vectors.json ../engine/demo_sw.json ../tools/harvestly_bot_core.py ../tools/weather_providers.py lib/
cp ../brand/telegram-profile-512.png public/logo.png
cp ../brand/telegram-cards/dial-*.png public/cards/
echo "synced"
