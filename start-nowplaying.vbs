' Запускает nowplaying.py в фоне, без окна консоли.
' Положи ярлык на этот файл в папку автозагрузки (Win+R → shell:startup).
Set sh = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.Run "pythonw """ & folder & "nowplaying.py""", 0, False
