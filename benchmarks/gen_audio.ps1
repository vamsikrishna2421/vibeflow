# Generate hard test audio from asr_cases.json using Windows TTS.
# Speech is rendered FAST (rate +3) and across alternating voices to stress the
# speech-to-text models and surface real transcription errors.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$here = "C:\Users\vamsy\Documents\vibeflow\benchmarks"
$audio = Join-Path $here "audio"
New-Item -ItemType Directory -Force -Path $audio | Out-Null

$cases = Get-Content (Join-Path $here "asr_cases.json") -Raw | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name })
Write-Output ("voices: " + ($voices -join ', '))
$synth.Rate = 3   # fast — makes the models work harder

$i = 0
foreach ($c in $cases) {
  if ($voices.Count -gt 0) { $synth.SelectVoice($voices[$i % $voices.Count]) }
  $out = Join-Path $audio ("{0}.wav" -f $c.id)
  $synth.SetOutputToWaveFile($out)
  $synth.Speak([string]$c.text)
  $i++
}
$synth.SetOutputToNull()
$synth.Dispose()
Write-Output ("generated " + $cases.Count + " WAV files in " + $audio)
