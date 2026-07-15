# Build Script for Harmulizer Pro
# Builds a standalone Windows executable

Write-Host "Building Harmulizer Pro..." -ForegroundColor Green

# Install/Update PyInstaller in venv
Write-Host "Checking PyInstaller in virtual environment..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install pyinstaller

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Build executable
Write-Host "Building executable..." -ForegroundColor Green
.\.venv\Scripts\pyinstaller harmulizer.spec --clean

# Check if build succeeded
if (Test-Path "dist\Harmulizer_Pro.exe") {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "Executable location: dist\Harmulizer_Pro.exe" -ForegroundColor Cyan
    Write-Host "`nFile size:" -ForegroundColor Yellow
    Get-Item "dist\Harmulizer_Pro.exe" | Select-Object Name, @{Name="Size (MB)";Expression={[math]::Round($_.Length / 1MB, 2)}}
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}
