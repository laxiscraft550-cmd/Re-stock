param([ValidateSet('usb','pc')]$a)
$ErrorActionPreference = 'Stop'
$pc = 'C:\bot-ofertas'; $usb = $PSScriptRoot
function Get-Copia($d) { Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" | Where-Object { $_.ExecutablePath -like "$d\*" -or $_.CommandLine -like "*$d\*bot.py*" } }
function Copy-Base($de, $h) {
    if (Test-Path "$h\ofertas.db") { Copy-Item "$h\ofertas.db" "$h\ofertas.anterior.db" -Force }
    Copy-Item "$de\ofertas.db" "$h\ofertas.db" -Force
    if ((Get-FileHash "$de\ofertas.db").Hash -ne (Get-FileHash "$h\ofertas.db").Hash) { throw 'La copia no coincide.' }
}
try {
    if (-not (Test-Path "$pc\ofertas.db")) { throw "Esto solo se usa en la PC donde esta $pc" }
    if (Get-Copia $usb) { throw 'Primero cierra el bot del USB.' }
    if ($a -eq 'usb') {
        if ((Get-ScheduledTask BotOfertas).State -eq 'Disabled') { throw 'El bot ya fue pasado al USB. Usa iniciar.bat' }
        try {
            Disable-ScheduledTask BotOfertas | Out-Null; Stop-ScheduledTask BotOfertas; Start-Sleep 4
            # el lock de bot.py: si el puerto sigue ocupado, hay una copia viva
            $s = New-Object Net.Sockets.Socket([Net.Sockets.AddressFamily]::InterNetwork, 'Stream', 'Tcp')
            $s.Bind((New-Object Net.IPEndPoint([Net.IPAddress]::Loopback, 47391))); $s.Close()
            Copy-Item "$pc\.env" "$usb\.env" -Force
            Copy-Base $pc $usb
        } catch { Enable-ScheduledTask BotOfertas | Out-Null; Start-ScheduledTask BotOfertas; throw "No se pudo pasar; el bot sigue en la PC. $_" }
        'Listo: apagado en la PC. Abre iniciar.bat donde quieras usarlo.'
    } else {
        if ((Get-ScheduledTask BotOfertas).State -ne 'Disabled') { throw 'El bot ya esta en la PC.' }
        if (-not (Test-Path "$usb\ofertas.db")) { throw 'El USB no tiene datos.' }
        Copy-Base $usb $pc
        Enable-ScheduledTask BotOfertas | Out-Null; Start-ScheduledTask BotOfertas
        'Listo: el bot esta encendido en la PC otra vez.'
    }
} catch { "ERROR: $_"; exit 1 }
