@echo off
setlocal

set "BUNDLE_DIR=%~dp0"
set "APP_DIR=%BUNDLE_DIR%app"
set "DATA_DIR=%BUNDLE_DIR%data"
set "PYTHON_BIN=%BUNDLE_DIR%python\python.exe"
set "PORT=8787"
set "URL=http://127.0.0.1:%PORT%/"
set "HEALTH_URL=%URL%api/health"
set "WAIT_ATTEMPTS=30"

if not exist "%PYTHON_BIN%" (
  echo Portable Python was not found at %PYTHON_BIN%.
  pause
  exit /b 1
)

if not exist "%APP_DIR%\portable_webui_app.py" (
  echo Portable app files were not found at %APP_DIR%.
  pause
  exit /b 1
)

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"

set "ILAB_CONJURE_BUNDLE_DIR=%BUNDLE_DIR%"
set "ILAB_CONJURE_DATA_DIR=%DATA_DIR%"
set "PYTHONPATH=%APP_DIR%;%APP_DIR%\.deps"
set "CERTIFI_CA_BUNDLE=%BUNDLE_DIR%python\Lib\site-packages\certifi\cacert.pem"
if exist "%CERTIFI_CA_BUNDLE%" (
  set "SSL_CERT_FILE=%CERTIFI_CA_BUNDLE%"
  set "REQUESTS_CA_BUNDLE=%CERTIFI_CA_BUNDLE%"
)
set "AUTH_SETTINGS_PATH=%DATA_DIR%\webui-auth-settings.json"
"%PYTHON_BIN%" -m codex_image.webui.startup_auth --settings-path "%AUTH_SETTINGS_PATH%" >nul
set "LOG_FILE=%DATA_DIR%\logs\webui-server.log"

cd /d "%APP_DIR%"

echo Starting iLab CONJURE at %URL%
echo Data directory: %DATA_DIR%
echo Writing server log to %LOG_FILE%

call :is_webui_ready
if %ERRORLEVEL% EQU 0 (
  echo WebUI is already running at %URL%
  start "" "%URL%"
  exit /b 0
)

start "iLab CONJURE WebUI" /b "%PYTHON_BIN%" -m uvicorn portable_webui_app:app --host 127.0.0.1 --port %PORT% --no-access-log >> "%LOG_FILE%" 2>&1

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
"%PYTHON_BIN%" -c "import sys, urllib.request; response = urllib.request.urlopen(sys.argv[1], timeout=1); sys.exit(0 if response.status == 200 else 1)" "%HEALTH_URL%" >nul 2>nul
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
