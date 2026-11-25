# Arma la version para USB con el Python de esta PC. No copia el token ni los datos.
param($Destino = 'C:\bot-ofertas-portatil')
$ErrorActionPreference = 'Stop'
if (Test-Path $Destino) { throw "Ya existe $Destino" }
$base = & "$PSScriptRoot\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
robocopy $base "$Destino\python" /E /NFL /NDL /NJH /NJS /XD site-packages test tests __pycache__ Doc tcl tkinter idlelib Scripts include libs Tools ensurepip | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Fallo la copia de Python' }
robocopy "$PSScriptRoot\.venv\Lib\site-packages" "$Destino\python\Lib\site-packages" /E /NFL /NDL /NJH /NJS /XD __pycache__ pip | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Fallo la copia de paquetes' }
Copy-Item "$PSScriptRoot\bot.py","$PSScriptRoot\datos.py","$PSScriptRoot\extractor.py","$PSScriptRoot\reglas.py","$PSScriptRoot\pruebas.py" $Destino
Copy-Item "$PSScriptRoot\portatil\*" $Destino
"Creado en $Destino"
