@echo off
setlocal
if "%TH08_WINDOWS_PYTHON%"=="" exit /b 80
start "" /b th08.exe
if "%TH08_RETAIL_LIFE_DECREMENT%"=="1" exit /b 0
if "%TH08_PATCHER%"=="" exit /b 81
"%TH08_WINDOWS_PYTHON%" "%TH08_PATCHER%"
exit /b %errorlevel%
