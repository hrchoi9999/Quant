# Trading Sign Thread Working Rules

## Purpose

This document fixes the operating rules for the trading timing model work handled in this thread.

## Mandatory rules

1. All work for this thread must be created, edited, and stored under `D:\Quant\trading_sign`.
2. All documents for this thread must be stored under `D:\Quant\trading_sign\docs`.
3. Paths outside `D:\Quant\trading_sign` are read-only for this thread.
4. No files outside `D:\Quant\trading_sign` may be modified by this thread.
5. If work outside this folder is required, a written work request must be created and handed off instead of editing the target directly.

## Allowed use of external folders

The following use is allowed for paths outside this workspace:

- read existing code for reference
- inspect schemas, backtest engines, and research outputs
- copy design ideas into new files inside `D:\Quant\trading_sign`

The following use is not allowed for paths outside this workspace:

- editing source files
- moving files
- deleting files
- adding docs or reports
- updating configuration

## Delivery principle

When this thread produces a design or implementation that depends on another thread or workspace, the dependency must be documented as a handoff request under:

- `D:\Quant\trading_sign\docs`

## Current objective

The first objective is to design and develop a V1 timing overlay model for buy and sell timing on top of existing Quant-selected candidates, while keeping all new work isolated inside this workspace.
