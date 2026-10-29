# sync-to-dsh.ps1 - Sincroniza las skills de este repo con las raices locales que DSH autocarga.
#
# DSH descubre skills en el sistema de ficheros LOCAL (~/.dsh/skills y
# <projectRoot>/.dsh/skills), nunca en el servidor. Por eso las skills de .skills/ se
# copian a ~/.dsh/skills y cada copia lleva un banner con el sha256 del fichero de
# origen.
#
# Uso (desde la maquina local, con la clave de sync autorizada en el servidor):
#   pwsh -File sync-to-dsh.ps1                  # sincroniza lo que este desactualizado
#   pwsh -File sync-to-dsh.ps1 -Mode Check      # solo comprueba (exit 1 si hay drift)
#
# Resincroniza siempre despues de modificar cualquier SKILL.md del repo.

# sync-to-dsh.ps1
[CmdletBinding()]
param(
    [string] $SshHost = '192.168.192.103',
    [int]    $SshPort = 22,
    [string] $SshUser = 'odoo',
    [string] $IdentityFile = (Join-Path $env:USERPROFILE '.ssh\id_ed25519_dsh_sync'),
    [string] $RemotePath = '/opt/pharmadus/odoo/custom/src/pharmadus',
    [ValidateSet('Sync', 'Check')] [string] $Mode = 'Sync'
)

$ErrorActionPreference = 'Stop'

$skills = @(
    [pscustomobject]@{ Name = 'odoo-18';       SourceDir = 'odoo-18.0' }
    [pscustomobject]@{ Name = 'odoo-dev';      SourceDir = 'odoo-dev' }
    [pscustomobject]@{ Name = 'project-graph'; SourceDir = 'project-graph' }
)

if (-not (Test-Path $IdentityFile)) { throw "No existe la clave de sync: $IdentityFile" }

# --- raices locales donde DSH busca skills -----------------------------------
function ConvertFrom-DshPathName {
    param([string] $Name)

    $padded = $Name
    $pad = $padded.Length % 4
    if ($pad) { $padded += '=' * (4 - $pad) }
    try { return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($padded)) } catch { return $null }
}

# DSH descubre skills en ~/.dsh/skills y <projectRoot>/.dsh/skills. El espejo que dejaba
# el antiguo plugin dsh-ssh (~/.dsh/remote/<hostId>/<ruta remota en base64>/.dsh/skills)
# ya no se monta, asi que el destino real es la raiz global. Los espejos que sigan
# existiendo se mantienen al dia para no dejar copias huerfanas, pero su ausencia ya
# no es un error.
$skillRoots = @()

$globalRoot = Join-Path $env:USERPROFILE '.dsh\skills'
if (-not (Test-Path $globalRoot)) {
    New-Item -ItemType Directory -Force -Path $globalRoot | Out-Null
}
$skillRoots += [pscustomobject]@{ Root = $globalRoot; Label = 'local' }

# DSH nombra cada carpeta de espejo con la ruta remota en base64 SIN padding, asi que
# decodificamos los nombres existentes en vez de codificar la ruta.
$remoteRoot = Join-Path $env:USERPROFILE '.dsh\remote'
if (Test-Path $remoteRoot) {
    foreach ($hostDir in (Get-ChildItem $remoteRoot -Directory -ErrorAction SilentlyContinue)) {
        foreach ($pathDir in (Get-ChildItem $hostDir.FullName -Directory -ErrorAction SilentlyContinue)) {
            if ((ConvertFrom-DshPathName $pathDir.Name) -eq $RemotePath) {
                $skillRoots += [pscustomobject]@{
                    Root  = Join-Path $pathDir.FullName '.dsh\skills'
                    Label = "espejo:$(($hostDir.Name -split '-')[0])"
                }
            }
        }
    }
}

$sshCommon = @(
    '-i', $IdentityFile, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
    '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=10',
    '-o', 'StrictHostKeyChecking=accept-new', '-p', "$SshPort", "$SshUser@$SshHost"
)

function Get-RemoteSkill {
    param([string] $SourceDir)

    $file = "$RemotePath/.skills/$SourceDir/SKILL.md"
    $cmd = "sha256sum '$file' | cut -d' ' -f1; stat -c%s '$file'; gzip -c '$file' | base64 -w0"
    $out = & ssh @sshCommon $cmd 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ssh fallo al leer $file`n$($out -join "`n")" }

    $lines = @($out | Where-Object { $_ -is [string] -and $_.Trim() -ne '' })
    if ($lines.Count -lt 3) { throw "Respuesta inesperada del servidor para $file" }

    $sha = $lines[0].Trim()
    $bytes = [int]$lines[1].Trim()
    $payload = (($lines[2..($lines.Count - 1)]) -join '').Trim()
    if ($sha -notmatch '^[0-9a-f]{64}$') { throw "sha256 invalido para $file : $sha" }
    if ($payload -notmatch '^[A-Za-z0-9+/=]+$') { throw "payload base64 invalido para $file" }

    [pscustomobject]@{ File = $file; Sha256 = $sha; Bytes = $bytes; Payload = $payload }
}

function Expand-GzipBase64 {
    param([string] $Payload)

    $raw = [Convert]::FromBase64String($Payload)
    $ms = New-Object System.IO.MemoryStream(, $raw)
    $gz = New-Object System.IO.Compression.GZipStream($ms, [System.IO.Compression.CompressionMode]::Decompress)
    $sr = New-Object System.IO.StreamReader($gz, [Text.Encoding]::UTF8)
    try { $sr.ReadToEnd() } finally { $sr.Dispose(); $gz.Dispose(); $ms.Dispose() }
}

function Get-BannerSha {
    param([string] $Path)

    if (-not (Test-Path $Path)) { return $null }
    $text = [System.IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    $m = [regex]::Match($text, 'sha256 origen:\s*([0-9a-f]{64})')
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

function Get-LocalBody {
    param([string] $Path)

    # Reconstruye el texto de origen a partir de la copia: quita la linea del banner y
    # la linea vacia que se insertan tras el frontmatter.
    if (-not (Test-Path $Path)) { return $null }
    $lines = [System.IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) -split "`n"
    $idx = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith('<!-- COPIA LOCAL SINCRONIZADA')) { $idx = $i; break }
    }
    if ($idx -lt 0) { return $null }
    $rest = @($lines[($idx + 1)..($lines.Count - 1)])
    if ($rest.Count -gt 0 -and $rest[0] -eq '') { $rest = @($rest[1..($rest.Count - 1)]) }
    return (@($lines[0..($idx - 1)]) + $rest) -join "`n"
}

function New-SkillCopy {
    param(
        [string] $RemoteFile, [string] $Sha, [int] $Bytes, [string] $Payload, [string] $Target
    )

    $text = Expand-GzipBase64 $Payload
    $lines = $text -split "`n"

    # El banner se inserta justo despues del frontmatter YAML para no romperlo.
    $close = -1; $seen = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].TrimEnd() -eq '---') { $seen++; if ($seen -eq 2) { $close = $i; break } }
    }

    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm')
    $banner = "<!-- COPIA LOCAL SINCRONIZADA para DSH. Origen: $RemoteFile | sha256 origen: $Sha | bytes origen: $Bytes | sincronizada: $stamp. Si el sha256 del origen cambia, resincroniza: ver skill pharmadus-repo-skills. -->"

    $body = if ($close -ge 0) {
        @($lines[0..$close]) + @($banner, '') + @($lines[($close + 1)..($lines.Count - 1)])
    } else {
        @($banner, '') + $lines
    }

    $dir = Split-Path -Parent $Target
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText($Target, ($body -join "`n"), (New-Object Text.UTF8Encoding($false)))
}

# --- sincronizacion ----------------------------------------------------------
$results = @()
$pending = 0

foreach ($skill in $skills) {
    $info = Get-RemoteSkill -SourceDir $skill.SourceDir

    foreach ($skillRoot in $skillRoots) {
        $target = Join-Path $skillRoot.Root "$($skill.Name)\SKILL.md"
        $localSha = Get-BannerSha $target

        $state = if ($null -eq $localSha) { 'falta' }
                 elseif ($localSha -ne $info.Sha256) { 'desactualizada' }
                 elseif ((Get-LocalBody $target) -ne (Expand-GzipBase64 $info.Payload)) { 'alterada' }
                 else { 'al dia' }

        if ($state -ne 'al dia') {
            $pending++
            if ($Mode -eq 'Sync') {
                New-SkillCopy -RemoteFile $info.File -Sha $info.Sha256 -Bytes $info.Bytes -Payload $info.Payload -Target $target
                $state = 'sincronizada'
            }
        }

        $results += [pscustomobject]@{
            Skill  = $skill.Name
            Host   = $skillRoot.Label
            Estado = $state
            Sha256 = $info.Sha256.Substring(0, 12)
            Bytes  = $info.Bytes
        }
    }
}

$results | Format-Table -AutoSize
Write-Host ''

if ($Mode -eq 'Check') {
    if ($pending -gt 0) {
        Write-Host "$pending copia(s) desactualizada(s) de $($results.Count). Ejecuta sin -Mode Check para sincronizar."
        exit 1
    }
    Write-Host "Todo al dia: $($results.Count) copia(s) verificadas."
    exit 0
}

if ($pending -eq 0) {
    Write-Host "Nada que hacer: $($results.Count) copia(s) ya estaban al dia."
} else {
    Write-Host "Sincronizadas $pending copia(s) de $($results.Count). El catalogo de DSH se refresca en segundos."
}
