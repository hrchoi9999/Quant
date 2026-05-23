# Quant Git and Backup Operation Policy

Updated: 2026-05-23

## Purpose

This document defines the minimum operating rules for keeping the Quant project recoverable and safe to maintain.

## Git Policy

- Use Git for source code, scripts, schemas, configuration templates, and operating documents.
- Do not use Git for local secrets, database files, model artifacts, generated web payloads, reports, or temporary files.
- Commit and push after each meaningful work unit:
  - pipeline or collector changes
  - strategy model logic changes
  - AI model training or evaluation code changes
  - E-series/ETF model code changes
  - admin/public payload builder code changes
  - operating policy or documentation changes
- Keep commits focused. Do not bundle unrelated research outputs and production code changes when avoidable.
- Push to `origin/main` after a successful local commit when the change is intended to be preserved.
- Quant thread must not directly edit QuantService or QuantMarket code. Use request documents for cross-thread work.

## Excluded From Git

The following should remain local or be handled by backup/artifact storage:

- `data/**/*.db`, SQLite WAL/SHM files
- `data/models/**/*.joblib`
- generated model metadata under `data/models`
- `service_platform/web/**/current/*.json`
- `service_platform/web/**/history/*.json`
- `trading_sign/data/**/*.db`
- local API keys, app keys, secret keys, tokens, and credentials
- `_tmp`, `reports`, `logs`, virtual environments, cache directories

## Backup Policy

- Run daily Quant backup after the daily pipeline is complete.
- Current scheduled task: `Quant Daily Backup`.
- Default backup destination: `D:\QuantBackup\Quant`.
- Keep latest 14 Quant ZIP backups and latest 14 Git bundles.
- Backup ZIP excludes heavy transient directories such as `.git`, `_tmp`, and `venv64`.
- Git bundle is created separately to preserve repository history.

## Backup Validation Policy

- Validate the latest Quant backup at least weekly.
- Validation should check:
  - latest backup ZIP exists and is readable
  - ZIP contains expected top-level project files/directories
  - Git bundle exists and passes `git bundle verify`
  - latest backup date is within the expected operating window
- Failed validation must be treated as an operating issue before the next major pipeline run.

## Recovery Notes

- For code recovery, prefer GitHub `origin/main`.
- For full local state recovery, use the latest `Quant_*.zip` plus matching `Quant_git_*.bundle`.
- For databases and generated outputs, use the latest full backup unless a more recent operating DB is available.
