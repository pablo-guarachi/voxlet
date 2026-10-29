@echo off
REM Build <APP_ID>.exe (APP_ID read from config.py) with PyInstaller.
REM Run with the venv activated (.venv\Scripts\activate first).
REM
REM Output: dist\<APP_ID>\<APP_ID>.exe (onedir mode, fast startup)

setlocal
cd /d "%~dp0"

if not exist .venv (
    echo ERROR: venv not found. Create it with: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Product name: single source = config.py (APP_ID derived from APP_NAME)
set APP_ID=
for /f "usebackq delims=" %%N in (`python -c "import config; print(config.APP_ID)"`) do set APP_ID=%%N
if "%APP_ID%"=="" (
    echo ERROR: could not read APP_ID from config.py
    exit /b 1
)
echo === App: %APP_ID% ===

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APP_ID%.spec del /q %APP_ID%.spec

echo === Building with PyInstaller ===
pyinstaller ^
    --name %APP_ID% ^
    --windowed ^
    --icon icons\app.ico ^
    --add-data "icons;icons" ^
    --add-data "assets;assets" ^
    --add-data "theme.qss;." ^
    --add-binary ".venv\Scripts\cublas64_12.dll;." ^
    --add-binary ".venv\Scripts\cublasLt64_12.dll;." ^
    --add-binary ".venv\Scripts\cudnn64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_adv64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_cnn64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_engines_precompiled64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_engines_runtime_compiled64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_graph64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_heuristic64_9.dll;." ^
    --add-binary ".venv\Scripts\cudnn_ops64_9.dll;." ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    --collect-all sounddevice ^
    --collect-all PySide6 ^
    --collect-all pycaw ^
    --collect-all comtypes ^
    --collect-all onnxruntime ^
    app.py

if errorlevel 1 (
    echo === BUILD FAILED ===
    exit /b 1
)

echo.
echo === BUILD OK ===
echo Executable: dist\%APP_ID%\%APP_ID%.exe
echo.
echo Note:
echo  - The first run downloads the Whisper model (~3GB) to %%USERPROFILE%%\.cache\huggingface
echo  - Ollama (optional) must be installed and running separately
echo  - The executable is not signed: Windows SmartScreen may warn on first launch
endlocal
