# Redbot User Report Structure

## Purpose
This document fixes the user-facing portfolio recommendation report structure for Redbot.
It translates internal model outputs into a format suitable for web, PDF, and email channels.

## Core Principles
- User-facing reports must explain decisions, not expose engine internals.
- Internal model names such as `S2`, `S3`, `S4`, `S5`, `S6`, `Router` are hidden by default.
- Reports should prioritize recommendation result, market diagnosis, allocation, risk guidance, and recent performance.
- The same report payload should be reusable across web cards, PDF summaries, and email digests.

## Top-Level Report Sections
1. Header
2. Executive Summary
3. Current Market Diagnosis
4. Recommended Model Explanation
5. Recommended Portfolio Allocation
6. Why This Portfolio
7. Risk And Volatility Guide
8. Recent Performance Summary
9. Changes Since Previous Recommendation
10. Disclaimer And Caution

## Header
Required fields:
- report_title
- generated_at
- user_model_name
- service_profile
- report_version

## Executive Summary
Required fields:
- current_recommendation
- market_view
- primary_reason
- risk_level

## Current Market Diagnosis
Required fields:
- current_regime
- regime_summary
- current_response

## Recommended Model Explanation
Required fields:
- model_name
- model_character
- target_user_type
- core_role

## Recommended Portfolio Allocation
Each row should support:
- asset_group
- display_name
- target_weight
- role_summary
- source_type

## Why This Portfolio
Expected shape:
- 3 to 5 plain-language bullets
- avoid direct exposure of technical indicators

## Risk And Volatility Guide
Required fields:
- risk_level
- expected_drawdown_note
- suitable_investor_type
- suggested_holding_period

## Recent Performance Summary
Recommended visible metrics:
- 1Y CAGR
- FULL CAGR
- MDD
- Sharpe
Optional expanded metrics:
- 2Y, 3Y, 5Y

## Changes Since Previous Recommendation
Recommended fields:
- increased_assets
- decreased_assets
- change_reason

## Disclaimer And Caution
Must include:
- investment risk warning
- past performance disclaimer
- informational purpose statement
- final decision responsibility statement

## User-Facing vs Internal Data
User-facing:
- user_model_name
- service_profile
- market_view summary
- portfolio allocation summary
- risk label
- recent performance summary
- change summary
- disclaimer

Internal-only:
- internal model ids
- regime thresholds
- signal rules
- router decision internals
- detailed technical indicators
- raw optimization logic

## Output Channels
- Web: card + expandable sections
- PDF: one-to-two page summary
- Email: short digest using the same payload

## Payload Rule
The canonical payload should be JSON.
Markdown and HTML are render targets generated from that payload.
