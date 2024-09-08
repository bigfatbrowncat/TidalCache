import os, subprocess
import winreg
import PyInstaller.__main__

# Build the executable
PyInstaller.__main__.run([
    'TidalCache.spec', '-y'
])

# Make the nsis installer
aReg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
aKey = winreg.OpenKey(aReg, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\NSIS')
sValue = winreg.QueryValueEx(aKey, "InstallLocation")
makensispath = os.path.join(sValue[0], "makensis.exe")
subprocess.call([makensispath, "TidalCache.nsi"])
