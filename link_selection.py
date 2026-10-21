"""Read only an explicit selection through Windows UI Automation; no clipboard changes."""
import base64
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def media_link(text):
    value=str(text or '').strip()
    if len(value)>8192 or any(c.isspace() or ord(c)<32 for c in value):return None
    try:
        url=urlsplit(value)
        if url.scheme.lower() not in ('http','https') or not url.hostname or url.username or url.password:return None
        _=url.port
    except ValueError:return None
    return value


def selected_link():
    if sys.platform!='win32':return None
    script=r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$e=[System.Windows.Automation.AutomationElement]::FocusedElement
if($null -eq $e -or $e.Current.IsPassword){exit}
$p=$null
if($e.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$p)){
 $parts=@($p.GetSelection() | ForEach-Object {$_.GetText(8193)})
 if($parts.Count -eq 1){[Console]::Write($parts[0])}
}
'''
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        result=subprocess.run([str(executable),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=4,creationflags=subprocess.CREATE_NO_WINDOW)
        # Windows PowerShell console encoding is explicitly set to UTF-8 below.
        return media_link(result.stdout.decode('utf-8',errors='replace')) if result.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):return None
