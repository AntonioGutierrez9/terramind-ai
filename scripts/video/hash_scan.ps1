# Lists cells whose displayed text is ##### (column too narrow) on every sheet, as rendered by Microsoft Excel.
param([string]$Xlsx)
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Xlsx, 0, $true)
  $xl.Iteration = $true; $xl.MaxIterations = 200; $xl.CalculateFull()
  $total = 0
  foreach ($ws in $wb.Worksheets) {
    $hits = @()
    foreach ($c in $ws.UsedRange.Cells) {
      if ($c.HasFormula -or $c.Value2 -is [double]) {
        if ([string]$c.Text -match '^#+$') { $hits += $c.Address(0, 0) }
      }
    }
    $total += $hits.Count
    Write-Output ("{0}: {1} cell(s) showing ###{2}" -f $ws.Name, $hits.Count, $(if ($hits.Count) { ' e.g. ' + (($hits | Select-Object -First 5) -join ', ') } else { '' }))
  }
  Write-Output "TOTAL: $total"
  $wb.Close($false)
} finally { $xl.Quit(); [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null }
