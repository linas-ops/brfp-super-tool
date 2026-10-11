# BRFP Super Tool — baixa o Python embutido (python.org, pacote "embeddable") para runtime\python.
# Chamado pelo "BRFP Super Tool.bat" na primeira vez num computador; não precisa de Python nem de administrador.
#   -Pacotes   depois do Python, baixa também numpy, SciPy, OpenCV, Pillow e o servidor da Transfermarkt (comum\componentes.py)
# Versão, endereço e SHA-256 vêm de comum\componentes.json (o mesmo que o Super Tool usa).
param([switch]$Pacotes)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try {
    $comum = $PSScriptRoot
    $raiz = Split-Path -Parent $comum
    $m = (Get-Content -LiteralPath (Join-Path $comum 'componentes.json') -Raw -Encoding UTF8 | ConvertFrom-Json).python
    $rt = Join-Path $raiz 'runtime'
    $dl = Join-Path $rt 'downloads'
    $dest = Join-Path $rt 'python'
    $novo = "$dest.novo"
    $zip = Join-Path $dl $m.arquivo
    New-Item -ItemType Directory -Force -Path $dl | Out-Null
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

    Write-Host ''
    Write-Host ("  Baixando o Python {0} de python.org ({1} MB)..." -f $m.versao, [math]::Round($m.tamanho / 1MB))
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    $baixou = $false
    for ($i = 1; $i -le 3 -and -not $baixou; $i++) {
        try {
            if (Test-Path -LiteralPath $curl) {
                & $curl -L --fail --progress-bar --retry 2 -o $zip $m.url
                if ($LASTEXITCODE -ne 0) { throw "curl terminou com o código $LASTEXITCODE" }
            } else {
                (New-Object Net.WebClient).DownloadFile($m.url, $zip)
            }
            $baixou = $true
        } catch {
            Write-Host ("  Falhou: {0}" -f $_.Exception.Message)
            if ($i -lt 3) { Write-Host '  Tentando de novo...'; Start-Sleep -Seconds (2 * $i) }
        }
    }
    if (-not $baixou) { throw "Não foi possível baixar $($m.url). Verifique a conexão com a internet." }

    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $m.sha256) {
        Remove-Item -LiteralPath $zip -Force
        throw 'O arquivo baixado não confere (SHA-256 diferente). Tente de novo mais tarde.'
    }
    Write-Host '  Arquivo conferido (SHA-256). Instalando em runtime\python...'

    if (Test-Path -LiteralPath $novo) { Remove-Item -LiteralPath $novo -Recurse -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $novo)
    # isolado: só a biblioteca padrão e Lib\site-packages (nem pacotes do usuário, nem PYTHONPATH)
    [IO.File]::WriteAllText((Join-Path $novo $m.pth), "python312.zip`r`n.`r`nLib\site-packages`r`n", [Text.Encoding]::ASCII)
    [IO.File]::WriteAllText((Join-Path $novo 'brfp-runtime.json'), ('{"versao": "' + $m.versao + '", "origem": "' + $m.url + '"}'), [Text.Encoding]::ASCII)
    $sp = Join-Path $dest 'Lib\site-packages'
    if (Test-Path -LiteralPath $sp) {
        New-Item -ItemType Directory -Force -Path (Join-Path $novo 'Lib') | Out-Null
        Move-Item -LiteralPath $sp -Destination (Join-Path $novo 'Lib\site-packages')     # pacotes já instalados: mantém
    } else {
        New-Item -ItemType Directory -Force -Path (Join-Path $novo 'Lib\site-packages') | Out-Null
    }
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
    Rename-Item -LiteralPath $novo -NewName 'python'
    Remove-Item -LiteralPath $zip -Force
    if (-not (Get-ChildItem -LiteralPath $dl -Force)) { Remove-Item -LiteralPath $dl -Force }
    Write-Host '  Python pronto.'

    if ($Pacotes) {
        Write-Host ''
        Write-Host '  Baixando os pacotes (numpy, SciPy, OpenCV, Pillow, servidor da Transfermarkt)...'
        & (Join-Path $dest 'python.exe') -X utf8 (Join-Path $comum 'componentes.py') instalar tudo
        if ($LASTEXITCODE -ne 0) {
            Write-Host '  Os pacotes não foram instalados agora; cada ferramenta oferece o download quando for aberta.'
        }
    }
    exit 0
} catch {
    Write-Host ''
    Write-Host ('  ERRO: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
