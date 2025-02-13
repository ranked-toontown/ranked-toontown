@echo off
title Toontown Ranked: Main Game Launcher
set /P PPYTHON_PATH=<PPYTHON_PATH
set SERVICE_TO_RUN=CLIENT
cd ..\..

:main
    %PPYTHON_PATH% -m pip install -r requirements.txt
    %PPYTHON_PATH% -m launch.launcher.launch
    pause
goto :main