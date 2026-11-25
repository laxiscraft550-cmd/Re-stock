# Arma la carpeta para otra PC con el Python de esta. Incluye tu token: no la publiques.
param($Destino = 'C:\bot-ofertas-otra-pc')
$ErrorActionPreference = 'Stop'
if (Test-Path $Destino) { throw "Ya existe $Destino" }
$base = & "$PSScriptRoot\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
robocopy $base "$Destino\python" /E /NFL /NDL /NJH /NJS /XD site-packages test tests __pycache__ Doc tcl tkinter idlelib Scripts include libs Tools ensurepip | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Fallo la copia de Python' }
robocopy "$PSScriptRoot\.venv\Lib\site-packages" "$Destino\python\Lib\site-packages" /E /NFL /NDL /NJH /NJS /XD __pycache__ pip | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Fallo la copia de paquetes' }
'bot.py','datos.py','extractor.py','reglas.py','sync.py','pruebas.py','.env','portatil\iniciar.bat' | ForEach-Object { Copy-Item "$PSScriptRoot\$_" $Destino }
# Copia inicial: permite reconocer tu chat la primera vez (luego se actualiza sola por Telegram).
if (Test-Path "$PSScriptRoot\ofertas.db") { Copy-Item "$PSScriptRoot\ofertas.db" $Destino }
"Creado en $Destino"
$global:LASTEXITCODE = 0
