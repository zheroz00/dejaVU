# PowerShell script to build the executable in a clean environment
# Run this from PowerShell (not WSL)

Write-Host "Cleaning previous build and ALL caches..." -ForegroundColor Green
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, *.spec, .venv_build

# Clear PyInstaller cache
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:LOCALAPPDATA\pyinstaller

# Clear Python cache files
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Include *.pyc -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Creating clean virtual environment..." -ForegroundColor Green
python -m venv .venv_build

Write-Host "Activating environment..." -ForegroundColor Green
& .\.venv_build\Scripts\Activate.ps1

Write-Host "Installing dependencies..." -ForegroundColor Green
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Building executable with PyInstaller (CLEAN BUILD)..." -ForegroundColor Green
pyinstaller --clean --onefile --windowed --icon=dejavu.ico --add-data "dejavu.ico;." --hidden-import=src.gui --hidden-import=src.llm_summarizer --hidden-import=src.font --hidden-import=src.hotkey_manager --hidden-import=src.hotkey_settings_dialog --hidden-import=src.hotkey_config --hidden-import=src.blur_effect --name="dejaVU" ActivityMonitor.pyw

Write-Host "`nBuild complete! Executable is in: dist\dejaVU.exe" -ForegroundColor Green
Write-Host "You can now run dist\dejaVU.exe" -ForegroundColor Cyan

# Deactivate
deactivate
