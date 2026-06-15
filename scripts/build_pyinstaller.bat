@echo off
echo ============================================
echo  AI EVALUATOR — BUILD
echo ============================================

pip install pyinstaller --quiet

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

pyinstaller build.spec --clean

if %errorlevel% neq 0 (
    echo ERROR: Falló la compilación
    pause
    exit /b 1
)

echo Organizando distribución...

set DIST=dist\ai_evaluator_release

mkdir "%DIST%"
mkdir "%DIST%\prompts"
mkdir "%DIST%\logs"
mkdir "%DIST%\resultados"
mkdir "%DIST%\transcripciones"

copy dist\ai_evaluator.exe "%DIST%\ai_evaluator.exe"
copy config.json "%DIST%\config.json"
copy prompts\*.txt "%DIST%\prompts\"

if exist diccionario (
    mkdir "%DIST%\diccionario"
    copy diccionario\*.txt "%DIST%\diccionario\"
)

echo.
echo ============================================
echo  BUILD COMPLETADO — dist\ai_evaluator_release
echo ============================================
pause
