#!/bin/sh
echo "Toontown Ranked: Main Game Launcher"
echo
export PPYTHON_PATH=$(cat ../PPYTHON_PATH)
export SERVICE_TO_RUN=CLIENT
cd ../../../

$PPYTHON_PATH -m pip install -r requirements.txt
$PPYTHON_PATH -m launch.launcher.launch
sleep 1
