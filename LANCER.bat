@echo off
title KongoAnnonces - Demarrage
color 0A
echo.
echo  ============================================
echo   KongoAnnonces - Marketplace Congo
echo   Powered by NEXORA Digital Solutions
echo  ============================================
echo.

:: Tuer toute instance Python existante sur port 5050
echo  Arret de l'ancienne instance...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul

:: Verifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERREUR : Python n'est pas installe.
    echo  Telechargez Python sur https://python.org
    pause
    exit
)

:: Installer Flask + Pillow si necessaire
echo  Verification des dependances...
pip install flask pillow --quiet 2>nul

:: Creer le dossier data si inexistant
if not exist "data" mkdir data

:: Creer le dossier uploads si inexistant
if not exist "static\uploads" mkdir static\uploads

:: Initialiser la base de donnees
echo  Initialisation de la base de donnees...
python database.py

:: Ouvrir le navigateur (apres 2 secondes)
timeout /t 2 /nobreak >nul
start http://localhost:5050

:: Lancer l'application
echo.
echo  ============================================
echo   Site disponible sur : http://localhost:5050
echo   Appuyez sur Ctrl+C pour arreter
echo  ============================================
echo.
python app.py

pause
