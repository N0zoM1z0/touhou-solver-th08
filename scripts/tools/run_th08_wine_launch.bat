@echo off
setlocal
if "%TH08_WINDOWS_PYTHON%"=="" exit /b 80
if "%TH08_PATCHER%"=="" exit /b 81
start "" /b th08.exe
"%TH08_WINDOWS_PYTHON%" "%TH08_PATCHER%"
exit /b %errorlevel%
