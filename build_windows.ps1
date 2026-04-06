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

function Remove-DirectoryWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [string]$ProcessNameHint = "",
        [int]$MaxAttempts = 6,
        [int]$DelayMs = 1200
    )

    if (-not (Test-Path $TargetPath)) {
        return
    }

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            # Best-effort clear read-only attributes before deletion.
            cmd /c "attrib -R `"$TargetPath\*`" /S /D" *> $null
            Remove-Item -Recurse -Force $TargetPath -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 1 -and $ProcessNameHint) {
                Get-Process -Name $ProcessNameHint -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            }
            if ($attempt -ge $MaxAttempts) {
                throw "Failed to remove '$TargetPath' after $MaxAttempts attempts. Close apps/explorer windows that may lock files and retry. Last error: $($_.Exception.Message)"
            }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
}

if ($Clean) {
    Remove-DirectoryWithRetry -TargetPath "build\$AppName" -ProcessNameHint $AppName
    Remove-DirectoryWithRetry -TargetPath "$DistDir\$AppName" -ProcessNameHint $AppName
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r "requirements.txt"

# Resolve required ICU runtime DLLs for Qt6Core.
# - Prefer ICU DLLs shipped in the installed PySide6 package.
# - If required names are missing there, optionally use matching names from %WINDIR%\System32.
# Build fails if Qt6Core requires ICU and no source DLL is available for a required name.
$icuDllCandidates = @()
$requiredIcuNames = @()
try {
    $icuPlanJson = & $PythonExe -c "import json, os, pathlib, PySide6; from lp_resolver.app import _required_qtcore_icu_dll_names; root=pathlib.Path(PySide6.__file__).resolve().parent; qtcore=root/'Qt6Core.dll'; required=_required_qtcore_icu_dll_names(qtcore); candidates={}; [candidates.setdefault(p.name.lower(), str(p.resolve())) for p in root.rglob('icu*.dll') if p.is_file()]; windir=os.environ.get('WINDIR') or os.environ.get('SystemRoot'); system32=(pathlib.Path(windir)/'System32') if windir else None; [candidates.setdefault(name.lower(), str((system32/name).resolve())) for name in required if system32 and (system32/name).is_file()]; print(json.dumps({'required': required, 'candidates': candidates}))"
    $icuPlan = $icuPlanJson | ConvertFrom-Json
    if ($null -ne $icuPlan.required) {
        $requiredIcuNames = @($icuPlan.required | ForEach-Object { [string]$_ })
    }

    $candidateMap = @{}
    if ($null -ne $icuPlan.candidates) {
        foreach ($property in $icuPlan.candidates.PSObject.Properties) {
            $candidateMap[$property.Name.ToLowerInvariant()] = [string]$property.Value
        }
    }

    $missingRequiredIcu = @()
    foreach ($name in $requiredIcuNames) {
        $key = $name.ToLowerInvariant()
        $candidatePath = $null
        if ($candidateMap.ContainsKey($key)) {
            $candidatePath = $candidateMap[$key]
        }
        if (-not [string]::IsNullOrWhiteSpace($candidatePath) -and (Test-Path -LiteralPath $candidatePath)) {
            $icuDllCandidates += $candidatePath
        }
        else {
            $missingRequiredIcu += $name
        }
    }

    if ($missingRequiredIcu.Count -gt 0) {
        throw "Qt6Core imports ICU runtime DLL(s) that could not be located for bundling: $($missingRequiredIcu -join ', ')"
    }
}
catch {
    throw "Failed to resolve required ICU runtime DLLs for packaging. $($_.Exception.Message)"
}

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

$seenIcuDlls = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($candidate in $icuDllCandidates) {
    $path = [string]$candidate
    if ([string]::IsNullOrWhiteSpace($path)) {
        continue
    }
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }
    if ($seenIcuDlls.Add($path)) {
        $pyInstallerArgs += @("--add-binary", "$path;PySide6")
    }
}

if ($requiredIcuNames.Count -gt 0) {
    Write-Host "Bundling required ICU DLL(s): $($requiredIcuNames -join ', ')"
}

$pyInstallerArgs += "lp_resolver\\app.py"

& $PythonExe -m PyInstaller @pyInstallerArgs

$builtAppDir = Join-Path $DistDir $AppName
$env:LP_RESOLVER_BUILT_APP_DIR = (Resolve-Path $builtAppDir).Path
try {
    $icuVerifyJson = & $PythonExe -c "import json, os, pathlib; from lp_resolver.app import _required_qtcore_icu_dll_names; app_dir=pathlib.Path(os.environ['LP_RESOLVER_BUILT_APP_DIR']); qtcore=app_dir/'_internal'/'PySide6'/'Qt6Core.dll'; required=_required_qtcore_icu_dll_names(qtcore) if qtcore.exists() else []; missing=[name for name in required if not ((qtcore.parent/name).exists() or (app_dir/'_internal'/name).exists())]; print(json.dumps({'qtcore_exists': qtcore.exists(), 'required': required, 'missing': missing}))"
    $icuVerify = $icuVerifyJson | ConvertFrom-Json
}
finally {
    Remove-Item Env:LP_RESOLVER_BUILT_APP_DIR -ErrorAction SilentlyContinue
}

if (-not [bool]$icuVerify.qtcore_exists) {
    throw "Build verification failed: _internal\\PySide6\\Qt6Core.dll not found in output."
}
if ($null -ne $icuVerify.missing -and @($icuVerify.missing).Count -gt 0) {
    throw "Build verification failed: missing required ICU runtime DLL(s) in output: $(@($icuVerify.missing) -join ', ')"
}
if ($null -ne $icuVerify.required -and @($icuVerify.required).Count -gt 0) {
    Write-Host "Verified ICU runtime DLL(s) in output: $(@($icuVerify.required) -join ', ')"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $repoRoot\$DistDir\$AppName"
$mode = if ($FullQt) { "FullQt" } else { "Lean" }
Write-Host "Mode: $mode"

