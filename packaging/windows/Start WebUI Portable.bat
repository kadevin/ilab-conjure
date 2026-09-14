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

start "" /b "%PYTHON_BIN%" -m codex_image.webui.open_when_ready --health-url "%HEALTH_URL%" --url "%URL%" --attempts %WAIT_ATTEMPTS% --interval 1 >nul 2>nul
"%PYTHON_BIN%" -m codex_image.webui.server portable_webui_app:app --port %PORT% --no-access-log --timeout-graceful-shutdown 5 >> "%LOG_FILE%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"
if %SERVER_EXIT% NEQ 0 echo WebUI stopped with exit code %SERVER_EXIT%. Check %LOG_FILE%.
exit /b %SERVER_EXIT%

:is_webui_ready
"%PYTHON_BIN%" -c "import sys, urllib.request; response = urllib.request.urlopen(sys.argv[1], timeout=1); sys.exit(0 if response.status == 200 else 1)" "%HEALTH_URL%" >nul 2>nul
exit /b %ERRORLEVEL%
