@echo off
rem ==============================================================
rem DTC Knowledge Graph - Android APK Build & Signing Script
rem Pure ASCII Script adhering to Global Rule 7 Standard
rem ==============================================================

cd /d "%~dp0"

echo [INFO] DTC Knowledge Graph - APK Builder
echo [INFO] Working Directory: %CD%

rem Check for Android Studio bundled JBR or system JAVA_HOME
if exist "C:\Program Files\Android\Android Studio\jbr\bin\java.exe" (
    set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
    echo [INFO] Using Android Studio JBR: %JAVA_HOME%
) else if not defined JAVA_HOME (
    echo [WARNING] JAVA_HOME is not set. Trying system default java...
)

rem Locate Gradle Wrapper or Distribution
set "GRADLE_CMD=gradlew.bat"
if not exist "%GRADLE_CMD%" (
    if exist "C:\Users\%USERNAME%\.gradle\wrapper\dists\gradle-8.2-bin\bbg7u40eoinfdyxsxr3z4i7ta\gradle-8.2\bin\gradle.bat" (
        set "GRADLE_CMD=C:\Users\%USERNAME%\.gradle\wrapper\dists\gradle-8.2-bin\bbg7u40eoinfdyxsxr3z4i7ta\gradle-8.2\bin\gradle.bat"
    )
)

echo [INFO] Building signed Debug and Release APKs...
call "%GRADLE_CMD%" assembleDebug assembleRelease

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Gradle build failed with error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ==============================================================
echo [SUCCESS] APK Packaging and Signing Completed Successfully!
echo ==============================================================
echo.
echo [1] Debug APK  : app\build\outputs\apk\debug\app-debug.apk
echo [2] Release APK: app\build\outputs\apk\release\app-release.apk
echo.
pause
