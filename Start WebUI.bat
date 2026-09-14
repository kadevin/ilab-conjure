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

"%PYTHON_BIN%" -m codex_image.dependency_check --requirements "%PROJECT_DIR%requirements-webui.txt" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo Installing WebUI dependencies...
  "%PYTHON_BIN%" -m pip install --require-hashes -r requirements-webui.txt
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

start "" /b "%PYTHON_BIN%" -m codex_image.webui.open_when_ready --health-url "%HEALTH_URL%" --url "%URL%" --attempts %WAIT_ATTEMPTS% --interval 1 >nul 2>nul
"%PYTHON_BIN%" -m codex_image.webui.server codex_image.webui.app:app --port %PORT% --no-access-log --timeout-graceful-shutdown 5 >> "%LOG_FILE%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"
if %SERVER_EXIT% NEQ 0 echo WebUI stopped with exit code %SERVER_EXIT%. Check %LOG_FILE%.
exit /b %SERVER_EXIT%

:is_webui_ready
powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 1; if ($response.StatusCode -eq 200) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
exit /b %ERRORLEVEL%
