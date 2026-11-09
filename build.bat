@echo off
setlocal
chcp 65001 >nul
echo ========================================================
echo          SubDesktop Portable Build Script
echo ========================================================
echo.

rem Check Python Environment
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python environment not detected.
    if not "%1"=="--no-pause" pause
    exit /b 1
)

rem Check and install dependencies
echo [1/3] Checking requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] Pip install returned non-zero code, continuing...
)

rem Clean old build cache
echo.
echo [2/3] Cleaning previous build artifacts...
if exist "build" rd /s /q "build"
if exist "dist\SubDesktop" rd /s /q "dist\SubDesktop"

rem Run PyInstaller
echo.
echo [3/3] Compiling standalone portable application (PyInstaller onedir)...
pyinstaller --noconfirm --onedir --windowed --name "SubDesktop" --hidden-import "PyQt5.QtWinExtras" --hidden-import "win32com.client" --hidden-import "send2trash" main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed! Check log output above.
    if not "%1"=="--no-pause" pause
    exit /b 1
)

rem Ensure profiles isolation folder exists in portable directory
if not exist "dist\SubDesktop\profiles" (
    mkdir "dist\SubDesktop\profiles"
)

echo.
echo ========================================================
echo [SUCCESS] SubDesktop build completed!
echo Portable Directory: dist\SubDesktop\
echo Main Executable:    dist\SubDesktop\SubDesktop.exe
echo ========================================================
echo.
if not "%1"=="--no-pause" pause
endlocal
