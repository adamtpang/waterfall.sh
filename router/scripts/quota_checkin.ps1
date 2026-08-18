# quota_checkin.ps1 -- native Windows check-in reminder, C in the A/B/C/D
# quota-safety plan. No third-party dependencies (msg.exe doesn't exist on
# Windows Home; this uses WinForms MessageBox, which ships on every edition).
#
# Runs waterfall's local Claude estimate (fast if cached, real scan if not)
# and shows it in a blocking dialog alongside a reminder to check Codex/Grok
# too, since neither exposes local usage data waterfall can read automatically
# (see CLAUDE.md's 2026-08-18 entry on this).

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$cliPath = Join-Path $repoRoot "router\cli.py"

$estimateOutput = & python3 $cliPath claude-estimate 2>&1 | Out-String

Add-Type -AssemblyName System.Windows.Forms
$message = @"
$estimateOutput
Also check: Codex and Grok's own usage panels (waterfall can't read
their usage locally -- see the dashboard's countermeasures section).

Run `waterfall dashboard` for the full picture across everything.
"@

[System.Windows.Forms.MessageBox]::Show(
    $message,
    "waterfall quota check-in",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
