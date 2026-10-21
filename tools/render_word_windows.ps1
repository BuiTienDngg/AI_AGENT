param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

# Optional local visual QA. Uses installed Word and Windows PDF rendering;
# it never attaches to a user's existing Word application instance.
$ErrorActionPreference = 'Stop'
$inputFile = (Resolve-Path -LiteralPath $DocumentPath).Path
$renderFolder = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $renderFolder -Force | Out-Null
$pdfFile = Join-Path $renderFolder (([System.IO.Path]::GetFileNameWithoutExtension($inputFile)) + '.pdf')
$wordApp = $null
$document = $null
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordApp.AutomationSecurity = 3
    $document = $wordApp.Documents.Open($inputFile, $false, $true, $false)
    $document.ExportAsFixedFormat($pdfFile, 17)
}
finally {
    if ($null -ne $document) {
        $document.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $wordApp) {
        $wordApp.Quit(0)
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordApp)
    }
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFolder,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfPageRenderOptions,Windows.Data.Pdf,ContentType=WindowsRuntime] | Out-Null
$asyncResultMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$asyncActionMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1

function Get-WinRTResult($Operation, [Type]$ResultType) {
    $task = $asyncResultMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}
function Wait-WinRTAction($Operation) {
    $task = $asyncActionMethod.Invoke($null, @($Operation))
    $task.Wait()
}

$pdfStorageFile = Get-WinRTResult ([Windows.Storage.StorageFile]::GetFileFromPathAsync($pdfFile)) ([Windows.Storage.StorageFile])
$pdf = Get-WinRTResult ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($pdfStorageFile)) ([Windows.Data.Pdf.PdfDocument])
$storageFolder = Get-WinRTResult ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($renderFolder)) ([Windows.Storage.StorageFolder])
for ($pageIndex = 0; $pageIndex -lt $pdf.PageCount; $pageIndex++) {
    $page = $pdf.GetPage($pageIndex)
    $stream = $null
    try {
        $name = 'page-' + ($pageIndex + 1) + '.png'
        $file = Get-WinRTResult ($storageFolder.CreateFileAsync($name, 1)) ([Windows.Storage.StorageFile])
        $stream = Get-WinRTResult ($file.OpenAsync(1)) ([Windows.Storage.Streams.IRandomAccessStream])
        $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $options.DestinationWidth = 1200
        Wait-WinRTAction ($page.RenderToStreamAsync($stream, $options))
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $page.Dispose()
    }
}
Write-Output ('Rendered ' + $pdf.PageCount + ' pages to ' + $renderFolder)
