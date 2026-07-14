# TalentBeacon Shared Server Setup

Use one running TalentBeacon server when multiple people need the same data.

## Why

`127.0.0.1` and `localhost` always mean "this computer only". If two laptops each open `127.0.0.1`, they are using two separate local apps, separate uploaded files, separate generated employee accounts, and separate matching results.

## Correct Team Flow

1. Start TalentBeacon on the main laptop:

```powershell
cd C:\Users\Himanshu\Desktop\CProjectsTalentBeacon
python run_5001.py
```

2. Find the main laptop IPv4 address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1' } | Select-Object IPAddress
```

3. Friends should open this URL from their laptop:

```text
http://MAIN-LAPTOP-IP:5001/login
```

Example:

```text
http://192.168.1.10:5001/login
```

## Important

Do not ask another laptop to run its own `python run.py` or open its own `127.0.0.1` if everyone must see the same employee accounts, projects, matches, and career results.
