@echo off
title ADMX Manager
echo Starting ADMX Manager...
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.7+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Run the application
pythonw admx_manager.py

if errorlevel 1 (
    echo.
    echo Error starting ADMX Manager.
    echo Trying with console output for debugging...
    echo.
    python admx_manager.py
    pause
)
