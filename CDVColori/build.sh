#!/usr/bin/env bash
# Compila CDVColori.exe (.NET Framework 4.8) in CDVColori/build/
set -euo pipefail
cd "$(dirname "$0")"
dotnet build -c Release -o build CDVColori.csproj
rm -f build/CDVColori.exe.config
echo "Pronto: $(pwd)/build/CDVColori.exe"
