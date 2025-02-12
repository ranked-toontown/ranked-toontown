@echo off
title Toontown Ranked: Main Game Launcher
set /P PPYTHON_PATH=<PPYTHON_PATH
set SERVICE_TO_RUN=CLIENT
cd ..\..

set /P TTOFF_LOGIN_TOKEN="Enter your name (default: player1): " || set TTOFF_LOGIN_TOKEN=player1

:main
    %PPYTHON_PATH% -m pip install -r requirements.txt
    %PPYTHON_PATH% -m launch.launcher.launch
    pause
goto :main