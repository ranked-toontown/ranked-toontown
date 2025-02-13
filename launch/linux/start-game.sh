#!/bin/sh
echo "Toontown Ranked: Main Game Launcher"
echo
export PPYTHON_PATH=$(cat ../PPYTHON_PATH)
export SERVICE_TO_RUN=CLIENT
cd ../../../

echo "Enter your name (default: player1): "
read -r loginToken
export TTOFF_LOGIN_TOKEN=${loginToken:="player1"}

while true
do
	$PPYTHON_PATH -m pip install -r requirements.txt
	$PPYTHON_PATH -m launch.launcher.launch
	sleep 5
done
