
@echo on
rem This script was created by Nuitka to execute 'relay.exe' with Python DLL being found.
set PATH=c:\users\dmitrykokotov\.pyenv\pyenv-win\versions\3.13.12;%PATH%
set PYTHONHOME=C:\Users\DmitryKokotov\.pyenv\pyenv-win\versions\3.13.12
set NUITKA_PYTHONPATH=D:\Essence_SC\lsrc\lcus-usb-relay-module-controller;C:\Users\DmitryKokotov\.pyenv\pyenv-win\versions\3.13.12\DLLs;C:\Users\DmitryKokotov\.pyenv\pyenv-win\versions\3.13.12\Lib;C:\Users\DmitryKokotov\.pyenv\pyenv-win\versions\3.13.12;C:\Users\DmitryKokotov\.pyenv\pyenv-win\versions\3.13.12\Lib\site-packages
rem "%~dp0relay.exe" %*
rem pyenv shell 3.13.12
python -m nuitka --enable-plugin=tk-inter --mode=onefile --windows-icon-from-ico="reviews_4142441.png" --windows-console-mode=disable .\relay.py

