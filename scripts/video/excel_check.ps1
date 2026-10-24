# Opens the workbook exported by TerraMind in Microsoft Excel (hidden), checks that an assumption change flows
# through the formulas, and exports the key sheets to PDF for the video. The workbook on disk is not modified.
param([string]$Xlsx, [string]$OutDir)
$ErrorActionPreference = 'Stop'
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Xlsx, 0, $true)
  $xl.Iteration = $true; $xl.MaxIterations = 200; $xl.MaxChange = 0.0001
  $xl.CalculateFull()
  Write-Output ("SHEETS: " + (($wb.Worksheets | ForEach-Object { $_.Name }) -join ' | '))
  $names = @($wb.Names | ForEach-Object { $_.Name })
  Write-Output ("NAMES (hard/irr): " + (($names | Where-Object { $_ -match 'hard|irr' }) -join ', '))
  $hardName = $names | Where-Object { $_ -match '^in_cost_hard_per_area$' } | Select-Object -First 1
  $out = $wb.Worksheets.Item('Outputs')
  if ($hardName) {
    $hard = $wb.Names.Item($hardName).RefersToRange
    $irr = $out.Range('B7')  # Equity IRR (levered, annualized)
    Write-Output ("IRR cell: Outputs!" + $irr.Address(0, 0) + " formula " + $irr.Formula)
    $h0 = $hard.Value2; $i0 = $irr.Value2
    $hard.Value2 = $h0 * 1.1
    $xl.CalculateFull()
    $i1 = $irr.Value2
    Write-Output ("LINK CHECK: hard cost {0} -> {1}; equity IRR {2:P2} -> {3:P2}" -f $h0, ($h0 * 1.1), $i0, $i1)
    $hard.Value2 = $h0
    $xl.CalculateFull()
  }
  foreach ($s in @('Outputs', 'Assumptions', 'Cash Flow', 'Sales', 'Construction')) {
    $ws = $wb.Worksheets.Item($s)
    $ps = $ws.PageSetup
    $ps.Orientation = 2
    $ps.Zoom = $false
    $ps.FitToPagesWide = 1
    $ps.FitToPagesTall = $false
    if ($s -in @('Cash Flow', 'Sales', 'Construction')) { $ps.PrintArea = '$A$1:$P$46'; $ps.FitToPagesTall = 1 }
    $ps.PrintGridlines = $true
    $ps.PrintHeadings = $true
    $ps.LeftMargin = 18; $ps.RightMargin = 18; $ps.TopMargin = 18; $ps.BottomMargin = 18
    $ws.ExportAsFixedFormat(0, (Join-Path $OutDir ($s.Replace(' ', '_') + '.pdf')))
  }
  $wb.Close($false)
} finally {
  $xl.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
}
