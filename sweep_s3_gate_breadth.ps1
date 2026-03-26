# sweep_s3_gate_breadth.ps1
# 사용법:
#   cd D:\Quant
#   .\venv64\Scripts\activate
#   powershell -ExecutionPolicy Bypass -File .\sweep_s3_gate_breadth.ps1
#
# 사전 준비:
#   1) 아래 파일을 D:\Quant\src\experiments\ 에 저장:
#      - run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py
#   2) 아래 요약 스크립트를 D:\Quant\ 에 저장:
#      - _summarize_s3_gate_sweep.py

$ErrorActionPreference = "Stop"
$proj = "D:\Quant"
$py = "$proj\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py"
$outdir = "$proj\reports\backtest_s3_dev"

# ---- 스윕 파라미터 ----
$openList  = @(0.45, 0.50, 0.52, 0.55, 0.58, 0.60)
$closeGap  = 0.04          # close = open - closeGap
$useSlopeList = @(1, 0)    # 1=엄격, 0=완화

# ---- 고정 파라미터 ----
$start = "2013-10-14"
$end   = "2026-02-23"
$topN  = 20
$minHold = 10

foreach($useSlope in $useSlopeList){
  foreach($open in $openList){
    $close = [math]::Max(0.0, $open - $closeGap)
    $tag = "core2_gate_swp_open$open`_close$close`_slope$useSlope".Replace(".","p")
    Write-Host "=== RUN tag=$tag (open=$open close=$close useSlope=$useSlope) ==="

    python $py `
      --start $start --end $end --top-n $topN --min-holdings $minHold `
      --tag $tag `
      --gate-enabled 1 `
      --gate-open-th $open --gate-close-th $close `
      --gate-use-slope $useSlope --gate-use-ma-stack 1
  }
}

# ---- 요약 생성 ----
$sumPy = "$proj\_summarize_s3_gate_sweep.py"
python $sumPy --glob "$outdir\s3_nav_hold_top${topN}_core2_gate_swp_*.csv" --out "$outdir\s3_gate_sweep_summary.csv"

Write-Host "`n[OK] summary -> $outdir\s3_gate_sweep_summary.csv"
