#!/bin/sh
set -e

echo "== Azure login (Gov) =="
az cloud set --name AzureUSGovernment
az login --service-principal --username "$AZURE_CLIENT_ID" --password "$AZURE_CLIENT_SECRET" --tenant "$AZURE_TENANT_ID" --allow-no-subscriptions --only-show-errors
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

echo "== Ensure the VM is running =="
az vm start --resource-group "$AZURE_RG" --name "$AZURE_VM_NAME" --only-show-errors

echo "== Stop app, swap files, restart, health check =="
PKG_URL="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/${PACKAGE_NAME}/${PACKAGE_VERSION}/${PACKAGE_FILE}"
PS="[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; \$d='${VM_DEPLOY_DIR}'; schtasks /End /TN TestMVC 2>&1 | Out-Null; Get-CimInstance Win32_Process -Filter \"Name='dotnet.exe'\" | Where-Object { \$_.CommandLine -like '*testmvc*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep 5; New-Item -ItemType Directory -Force -Path \$d | Out-Null; \$z=Join-Path \$d '${PACKAGE_FILE}'; Invoke-WebRequest -Uri '${PKG_URL}' -Headers @{'JOB-TOKEN'='${CI_JOB_TOKEN}'} -OutFile \$z -UseBasicParsing; tar -xzf \$z -C \$d; if (\$LASTEXITCODE -ne 0) { Write-Output 'EXTRACT-FAILED (files still locked)'; exit 1 }; Remove-Item \$z -Force; \$dll=Join-Path \$d 'TestMVC.UI.dll'; Write-Output ('DLL-TIMESTAMP ' + (Get-Item \$dll).LastWriteTimeUtc.ToString('u')); schtasks /Create /TN TestMVC /TR ('dotnet '+\$dll+' --urls http://0.0.0.0:${APP_PORT}') /SC ONSTART /RU SYSTEM /F; schtasks /Run /TN TestMVC; New-NetFirewallRule -DisplayName 'TestMVC ${APP_PORT}' -Direction Inbound -Action Allow -Protocol TCP -LocalPort ${APP_PORT} -ErrorAction SilentlyContinue | Out-Null; Start-Sleep 10; try { \$r=Invoke-WebRequest -Uri 'http://localhost:${APP_PORT}/' -UseBasicParsing -TimeoutSec 20; Write-Output ('APP-HTTP ' + \$r.StatusCode) } catch { Write-Output ('APP-NOT-UP: ' + \$_.Exception.Message) }"
az vm run-command invoke --resource-group "$AZURE_RG" --name "$AZURE_VM_NAME" --command-id RunPowerShellScript --scripts "$PS" --query "value[].message" -o tsv

echo "== Check above for EXTRACT-FAILED, DLL-TIMESTAMP (should be today) and APP-HTTP 200 =="
