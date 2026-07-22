@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "PORT=8787"
set "URL=http://127.0.0.1:%PORT%/"
set "HEALTH_URL=%URL%api/health"
set "WAIT_ATTEMPTS=30"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "PYTHON_BIN=%VENV_DIR%\Scripts\python.exe"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "SYSTEM_PYTHON=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo Python 3 was not found. Install Python 3 first.
    pause
    exit /b 1
  )
  set "SYSTEM_PYTHON=python"
)

if not exist "%PYTHON_BIN%" (
  echo Creating local virtual environment...
  %SYSTEM_PYTHON% -m venv "%VENV_DIR%"
  if %ERRORLEVEL% NEQ 0 (
    pause
    exit /b 1
  )
)

"%PYTHON_BIN%" -c "import fastapi, uvicorn, multipart, httpx" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo Installing WebUI dependencies...
  "%PYTHON_BIN%" -m pip install -r requirements-webui.txt
  if %ERRORLEVEL% NEQ 0 (
    pause
    exit /b 1
  )
)

echo Starting iLab CONJURE at %URL%
if not exist "output" mkdir "output"
set "AUTH_SETTINGS_PATH=%PROJECT_DIR%output\webui-auth-settings.json"
"%PYTHON_BIN%" -m codex_image.webui.startup_auth --settings-path "%AUTH_SETTINGS_PATH%" >nul
set "LOG_FILE=%PROJECT_DIR%output\webui-server.log"
echo Writing server log to %LOG_FILE%
call :is_webui_ready
if %ERRORLEVEL% EQU 0 (
  echo WebUI is already running at %URL%
  start "" "%URL%"
  exit /b 0
)

start "iLab CONJURE WebUI" /b "%PYTHON_BIN%" -m uvicorn codex_image.webui.app:app --host 127.0.0.1 --port %PORT% --no-access-log >> "%LOG_FILE%" 2>&1

call :wait_for_webui
if %ERRORLEVEL% EQU 0 (
  start "" "%URL%"
) else (
  echo WebUI did not become ready within 30 seconds. Check %LOG_FILE%.
  pause
  exit /b 1
)

echo WebUI server is running. Press Ctrl+C in this window to stop it.
:keep_server_window_open
timeout /t 3600 /nobreak >nul
goto keep_server_window_open

:is_webui_ready
powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 1; if ($response.StatusCode -eq 200) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
exit /b %ERRORLEVEL%

:wait_for_webui
set /a ATTEMPT=0
:wait_for_webui_loop
call :is_webui_ready
if %ERRORLEVEL% EQU 0 exit /b 0
set /a ATTEMPT+=1
if %ATTEMPT% GEQ %WAIT_ATTEMPTS% exit /b 1
timeout /t 1 /nobreak >nul
goto wait_for_webui_loop
