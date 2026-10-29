$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (-not $Days) { $Days = 7 }

function Try-Get([scriptblock]$Block) {
    try { & $Block } catch { $null }
}

function Iso($Date) {
    if ($Date) { ([datetime]$Date).ToString('s') } else { $null }
}

$result = [ordered]@{}

$result.system = Try-Get {
    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem
    $bios = Get-CimInstance Win32_BIOS
    $cpu = @(Get-CimInstance Win32_Processor)[0]
    [ordered]@{
        computer     = $env:COMPUTERNAME
        user         = "$env:USERDOMAIN\$env:USERNAME"
        domain       = $cs.Domain
        partOfDomain = [bool]$cs.PartOfDomain
        manufacturer = $cs.Manufacturer
        model        = $cs.Model
        serial       = $bios.SerialNumber
        os           = $os.Caption
        osVersion    = $os.Version
        osBuild      = $os.BuildNumber
        arch         = $os.OSArchitecture
        installDate  = Iso $os.InstallDate
        lastBoot     = Iso $os.LastBootUpTime
        cpu          = "$($cpu.Name)".Trim()
        cores        = $cpu.NumberOfCores
        threads      = $cpu.NumberOfLogicalProcessors
        cpuLoad      = $cpu.LoadPercentage
        ramTotalKB   = [double]$os.TotalVisibleMemorySize
        ramFreeKB    = [double]$os.FreePhysicalMemory
    }
}

$result.disks = @(Try-Get {
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [ordered]@{
            drive = $_.DeviceID
            label = $_.VolumeName
            fs    = $_.FileSystem
            size  = [double]$_.Size
            free  = [double]$_.FreeSpace
        }
    }
})

$result.physicalDisks = @(Try-Get {
    Get-PhysicalDisk | ForEach-Object {
        [ordered]@{
            name   = $_.FriendlyName
            media  = "$($_.MediaType)"
            health = "$($_.HealthStatus)"
            size   = [double]$_.Size
        }
    }
})

$result.network = @(Try-Get {
    Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=TRUE' | ForEach-Object {
        $cfg = $_
        $adapter = Get-CimInstance Win32_NetworkAdapter -Filter "Index=$($cfg.Index)"
        [ordered]@{
            name        = $adapter.NetConnectionID
            description = $cfg.Description
            mac         = $cfg.MACAddress
            dhcp        = [bool]$cfg.DHCPEnabled
            ipv4        = @($cfg.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })
            gateway     = @($cfg.DefaultIPGateway | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })
            dns         = @($cfg.DNSServerSearchOrder | Where-Object { $_ })
            speed       = [double]$adapter.Speed
        }
    }
})

$result.events = @(Try-Get {
    $filter = @{ LogName = 'System', 'Application'; Level = 1, 2; StartTime = (Get-Date).AddDays(-$Days) }
    Get-WinEvent -FilterHashtable $filter -MaxEvents 400 | ForEach-Object {
        [ordered]@{
            time    = Iso $_.TimeCreated
            log     = $_.LogName
            source  = $_.ProviderName
            id      = $_.Id
            level   = $_.Level
            message = ("$($_.Message)" -split "`r?`n")[0]
        }
    }
})

$jobs = @(Try-Get { Get-CimInstance Win32_PrintJob })
$result.printers = @(Try-Get {
    Get-CimInstance Win32_Printer | ForEach-Object {
        $name = $_.Name
        [ordered]@{
            name    = $name
            driver  = $_.DriverName
            port    = $_.PortName
            default = [bool]$_.Default
            offline = [bool]$_.WorkOffline
            network = [bool]$_.Network
            status  = $_.PrinterStatus
            error   = $_.DetectedErrorState
            jobs    = @($jobs | Where-Object { $_ -and $_.Name.StartsWith("$name,") }).Count
        }
    }
})

$result.services = @(Try-Get {
    Get-CimInstance Win32_Service -Filter "StartMode='Auto' AND State<>'Running'" | ForEach-Object {
        [ordered]@{ name = $_.Name; display = $_.DisplayName; state = $_.State }
    }
})

$result.antivirus = @(Try-Get {
    Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | ForEach-Object {
        [ordered]@{ name = $_.displayName; state = [int]$_.productState }
    }
})

$result.lastUpdate = Try-Get {
    $hotfix = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
    if ($hotfix) { [ordered]@{ id = $hotfix.HotFixID; date = Iso $hotfix.InstalledOn } }
}

$result.pendingReboot = [bool](Try-Get {
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
})

$result.battery = Try-Get {
    $b = @(Get-CimInstance Win32_Battery)[0]
    if ($b) { [ordered]@{ charge = $b.EstimatedChargeRemaining; status = $b.BatteryStatus } }
}

$json = $result | ConvertTo-Json -Depth 6 -Compress
if ($OutFile) { [IO.File]::WriteAllText($OutFile, $json, (New-Object Text.UTF8Encoding $false)) } else { $json }
