@echo off
title AI Loan Approval System Launcher
echo ===================================================
echo      Launching AI Loan Approval System
echo ===================================================
echo.
echo [1/2] Starting Main Chatbot & Health Check (Port 5000)...
start "AI Loan Chatbot (Port 5000)" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe app.py"

echo [2/2] Starting Admin Panel (Port 5001)...
start "AI Loan Admin Panel (Port 5001)" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe form_app.py"

echo.
echo ===================================================
echo Both servers are launching in separate windows!
echo.
echo   Chatbot:      http://localhost:5000
echo   Health Check: http://localhost:5000/health
echo   Admin Panel:  http://localhost:5001
echo ===================================================
timeout /t 3 >nul
start http://localhost:5000
start http://localhost:5000/health
start http://localhost:5001
