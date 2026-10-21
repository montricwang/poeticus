param(
  [string]$LlamaExe = 'D:\Poeticus\poeticus-data\tools\local-llm\llama-b11723-win-vulkan-x64\llama-server.exe',
  [string]$ModelPath = '\\wsl.localhost\Ubuntu\home\montric\projects\poeticus-data\models\Qwen3.5-4B\Qwen3.5-4B-Q4_K_M.gguf',
  [int]$Port = 8091,
  [int]$Context = 8192
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $LlamaExe -PathType Leaf)) {
  throw "llama-server.exe not found: $LlamaExe"
}
if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
  throw "GGUF not found: $ModelPath. Check your WSL distro name and model path."
}

Write-Host 'Local-only llama.cpp / Intel Iris Xe Vulkan'
Write-Host "Model: $ModelPath"
Write-Host "Endpoint: http://127.0.0.1:$Port/v1"
Write-Host 'Keep this terminal open. Stop with Ctrl+C after the batch finishes.'

# Keep the HTTP listener on Windows loopback only; do not expose essay data on LAN.
& $LlamaExe --model $ModelPath --host '127.0.0.1' --port $Port --ctx-size $Context --n-gpu-layers 99
