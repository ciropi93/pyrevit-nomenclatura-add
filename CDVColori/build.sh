#!/usr/bin/env bash
# Compila CDVColori.exe (.NET Framework 4.8) in CDVColori/build/ e lancia i test della logica.
set -euo pipefail
cd "$(dirname "$0")"
dotnet test tests/CDVColori.Tests.csproj -v quiet --nologo
dotnet build -c Release -o build CDVColori.csproj -v quiet --nologo
rm -f build/CDVColori.exe.config
echo "Pronto: $(pwd)/build/CDVColori.exe"
