@echo off
title Item Manager
echo Starting Item Manager...
echo.

py ItemManager.py

if errorlevel 1 (
    echo.
    echo ==============================================
    echo   Application crashed or closed with error.
    echo ==============================================
    pause
    exit /b
)
