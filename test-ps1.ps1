# Simple PowerShell test script
$ErrorActionPreference = "Stop"

Write-Host "Testing PowerShell script..."
Write-Host -ForegroundColor Green "✓ Green text works"
Write-Host -ForegroundColor Yellow "⚠ Yellow text works"
Write-Host -ForegroundColor Blue "ℹ Blue text works"
Write-Host -ForegroundColor Red "✗ Red text works"

$test = "value"
if ($test -eq "value") {
    Write-Host -ForegroundColor Green "✓ If/else works"
} else {
    Write-Host -ForegroundColor Red "✗ Should not see this"
}

Write-Host ""
Write-Host "All tests passed! The syntax is correct."
