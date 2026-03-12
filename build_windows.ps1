param(
    [string]$PythonExe = "python",
    [string]$AppName = "LPConflictResolver",
    [string]$DistDir = "dist\lp_resolver_app",
    [switch]$Clean,
    [switch]$FullQt
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path $PSScriptRoot
Set-Location $repoRoot

if ($Clean) {
    if (Test-Path "build\$AppName") { Remove-Item -Recurse -Force "build\$AppName" }
    if (Test-Path "$DistDir\$AppName") { Remove-Item -Recurse -Force "$DistDir\$AppName" }
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r "requirements.txt"

$pyInstallerArgs = @(
    "--noconfirm",
    "--onedir",
    "--name", $AppName,
    "--distpath", $DistDir,
    "--workpath", "build\$AppName",
    "--specpath", "build\$AppName",
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "PySide6.QtWidgets"
)

if ($FullQt) {
    $pyInstallerArgs += @("--collect-all", "PySide6")
}
else {
    $excludeModules = @(
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtConcurrent",
        "PySide6.QtDataVisualization",
        "PySide6.QtDBus",
        "PySide6.QtGraphs",
        "PySide6.QtHelp",
        "PySide6.QtHttpServer",
        "PySide6.QtLocation",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth",
        "PySide6.QtNfc",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio",
        "PySide6.QtSql",
        "PySide6.QtStateMachine",
        "PySide6.QtSvgWidgets",
        "PySide6.QtTest",
        "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "PySide6.QtWebView",
        "PySide6.QtXml",
        "PySide6.QtXmlPatterns"
    )

    foreach ($module in $excludeModules) {
        $pyInstallerArgs += @("--exclude-module", $module)
    }
}

$pyInstallerArgs += "lp_resolver\\app.py"

& $PythonExe -m PyInstaller @pyInstallerArgs

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $repoRoot\$DistDir\$AppName"
$mode = if ($FullQt) { "FullQt" } else { "Lean" }
Write-Host "Mode: $mode"

