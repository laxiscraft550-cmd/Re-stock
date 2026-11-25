# Deja el bot encendido: arranca al iniciar sesion y, si se cae, vuelve en 5 minutos.
# Para quitarlo: Unregister-ScheduledTask -TaskName BotOfertas
$py = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$accion = New-ScheduledTaskAction -Execute $py -Argument 'bot.py' -WorkingDirectory $PSScriptRoot
$cada5 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$op = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$usuario = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName BotOfertas -Action $accion -Trigger $cada5 -Settings $op -Principal $usuario -Force -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName BotOfertas
