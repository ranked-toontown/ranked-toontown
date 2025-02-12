title Toontown Ranked: Dedicated Server
set /P PPYTHON_PATH=<PPYTHON_PATH
cd ..\..

set WANT_ERROR_REPORTING=true

:main
    %PPYTHON_PATH% -m pip install -r requirements.txt
    %PPYTHON_PATH% -m toontown.toonbase.DedicatedServerStart
    pause
goto main
