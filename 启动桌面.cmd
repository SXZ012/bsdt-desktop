@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\BSDT内部工作台\BSDT内部工作台.exe" (
  start "" "%LOCALAPPDATA%\Programs\BSDT内部工作台\BSDT内部工作台.exe"
) else (
  echo 请先安装 outputs\installers\BSDT内部工作台 Setup 0.4.3.exe，然后通过桌面快捷方式打开。
  pause
)