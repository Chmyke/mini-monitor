# Fails when a long dash shows up in text a user can see.
# Rule: never an em dash (U+2014), nor an en dash (U+2013) between spaces, in interface text.
# Use a comma, a colon, parentheses, or rephrase. An en dash in a range ("1-5" written 1<U+2013>5)
# stays allowed, and so does a lone em dash standing for an empty value (a whole string or a
# whole cell). Comments are not interface text: a dash after a comment marker is ignored.
# Markdown, plain text, tests, and generated or vendored folders are not scanned. A line meant
# to hold a dash as data (a parser input, an escape table) carries the comment marker dash-ok.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File check-dashes.ps1 [-Root dir] [-Exclude regex,...]
# Canonical copy: Methode/modeles/check-dashes.ps1. Keep this file pure ASCII.
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string[]]$Exclude = @()
)
$ErrorActionPreference = 'Stop'
# git prints paths and the report prints lines in UTF-8, accents and dashes included.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$em = [string][char]0x2014
$spacedEn = ' ' + [char]0x2013 + ' '
# The same dash written as an escape or an entity still shows as a dash.
$escaped = '(?i)\\u\{?2014\}?|\\x\{2014\}|&mdash;|&#8212;|&#x2014;'  # dash-ok

# Scanned extensions, mapped to their line comment marker ('' = none).
$lineMarker = @{
    '.rs' = '//'; '.js' = '//'; '.mjs' = '//'; '.cjs' = '//'; '.ts' = '//'; '.tsx' = '//'
    '.jsx' = '//'; '.cs' = '//'; '.astro' = '//'; '.vue' = '//'; '.svelte' = '//'
    '.html' = ''; '.htm' = ''; '.css' = ''; '.json' = ''; '.xml' = ''; '.svg' = ''
    '.py' = '#'; '.ps1' = '#'; '.toml' = '#'; '.yaml' = '#'; '.yml' = '#'; '.sh' = '#'
}
# Tests follow the product (a renamed label breaks them) and may feed dashes as input data.
# Reference boards (*_ref, planches) and probes are not shipped.
$skipDirs = '(^|/)(\.[^/]+|node_modules|dist|target|vendor|docs|Documentation|research_notes|reports|test-results|venv|tests?|examples|planches|[^/]*_ref)/'
$localeDir = '(^|/)(locales?|i18n|lang|translations?)/'
$testFile ='([._](test|spec)\.[^/]+|(^|/)test_[^/]+)$'
# A line that carries this marker (in a comment) is data, not interface text.
$allowMarker = 'dash-ok'

# String delimiters of code files. Markup text is full of apostrophes: no tracking there, and a
# marker right after ':' (https://) is then taken for a URL.
$quoteChars = @{ '.rs' = '"'; '.cs' = '"'; '.py' = "`"'"; '.ps1' = "`"'"; '.toml' = "`"'"; '.yaml' = "`"'"
    '.yml' = "`"'"; '.sh' = "`"'"; '.js' = "`"'``"; '.mjs' = "`"'``"; '.cjs' = "`"'``"; '.ts' = "`"'``"
    '.tsx' = "`"'``"; '.jsx' = "`"'``" }

# Index of the first $token outside any string literal of $line, or -1.
function Find-Outside([string]$line, [string]$token, [string]$quotes) {
    $open = [char]0
    for ($i = 0; $i -lt $line.Length; $i++) {
        $c = $line[$i]
        if ($open -ne [char]0) {
            if ($c -eq '\') { $i++ } elseif ($c -eq $open) { $open = [char]0 }
            continue
        }
        if ($quotes.IndexOf($c) -ge 0) { $open = $c; continue }
        if ([string]::CompareOrdinal($line, $i, $token, 0, $token.Length) -eq 0) {
            if ($quotes -eq '' -and $token -eq '//' -and $i -gt 0 -and $line[$i - 1] -eq ':') { continue }
            return $i
        }
    }
    return -1
}

Push-Location $Root
try {
    $files = @(git -c core.quotepath=off ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) { throw "git ls-files failed in $Root" }
    $hits = New-Object System.Collections.Generic.List[string]
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    foreach ($file in $files) {
        $ext = [IO.Path]::GetExtension($file).ToLowerInvariant()
        # Translation tables are interface text whatever their extension (.txt, .ftl, .po).
        $locale = $file -match $localeDir -and $ext -in @('.txt', '.ftl', '.po', '.properties', '.strings', '.ini')
        if (-not ($lineMarker.ContainsKey($ext) -or $locale)) { continue }
        if ($file -match $skipDirs -or $file -match $testFile) { continue }
        $skip = $false
        foreach ($pattern in $Exclude) { if ($file -match $pattern) { $skip = $true; break } }
        if ($skip -or -not (Test-Path -LiteralPath $file)) { continue }
        $text = [IO.File]::ReadAllText((Join-Path $Root $file), $utf8)
        if (-not ($text.Contains($em) -or $text.Contains($spacedEn) -or $text -match $escaped)) { continue }
        $marker = if ($lineMarker.ContainsKey($ext)) { $lineMarker[$ext] } else { '' }
        $cStyle = $ext -notin @('.py', '.ps1', '.toml', '.yaml', '.yml', '.sh', '.json')
        $markup = $ext -in @('.html', '.htm', '.xml', '.svg', '.astro', '.vue', '.svelte')
        $quotes = if ($quoteChars.ContainsKey($ext)) { $quoteChars[$ext] } else { '' }
        $inBlock = $null
        $n = 0
        foreach ($line in ($text -split "`n")) {
            $n++
            # Remove block comments (/* */ and <!-- -->), which may span lines.
            $visible = ''
            $rest = $line
            while ($rest.Length -gt 0) {
                if ($inBlock) {
                    $end = $rest.IndexOf($inBlock)
                    if ($end -lt 0) { $rest = ''; break }
                    $rest = $rest.Substring($end + $inBlock.Length)
                    $inBlock = $null
                    continue
                }
                # A line comment ends the line, even when a block opener sits inside it.
                # A marker inside a string literal ("# Title", "https://") does not count.
                $openC = if ($cStyle) { Find-Outside $rest '/*' $quotes } else { -1 }
                $openM = if ($markup) { $rest.IndexOf('<!--') } else { -1 }
                $at = if ($marker) { Find-Outside $rest $marker $quotes } else { -1 }
                $first = @($openC, $openM, $at) | Where-Object { $_ -ge 0 } | Measure-Object -Minimum
                if ($first.Count -eq 0) { $visible += $rest; break }
                $cut = [int]$first.Minimum
                $visible += $rest.Substring(0, $cut)
                if ($cut -eq $at) { break }
                if ($cut -eq $openC) { $rest = $rest.Substring($cut + 2); $inBlock = '*/' }
                else { $rest = $rest.Substring($cut + 4); $inBlock = '-->' }
            }
            # A lone em dash standing for an empty value ('-' in a cell, >-< in markup) is allowed.
            $visible = [regex]::Replace($visible, "(['`"``>])$em(['`"``<])", '$1$2')
            if (($visible.Contains($em) -or $visible.Contains($spacedEn) -or $visible -match $escaped) -and
                -not $line.Contains($allowMarker)) {
                $hits.Add(('{0}:{1}: {2}' -f $file, $n, $line.Trim()))
            }
        }
    }
    if ($hits.Count -gt 0) {
        Write-Output 'Long dash in interface text (use a comma, a colon, parentheses, or rephrase):'
        $hits | ForEach-Object { Write-Output "  $_" }
        exit 1
    }
    Write-Output 'check-dashes: OK'
} finally { Pop-Location }
