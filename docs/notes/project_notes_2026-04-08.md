# Project Notes - 2026-04-08

## Purpose

This file stores working notes, ideas, and decisions made during the project.

## Today's decisions

- Keep Objective 1 and Objective 2 separated conceptually
- Use optimization rank-1 representative parameters for each strategy family
- Build Objective 1 as a realized-return matrix optimization problem
- Build Objective 2 as a prediction/signal matrix problem

## Objective 1 status

- Multi-strategy optimization and forward-style automation were organized
- Anchor-date and multi-horizon evaluation were implemented
- A full 5-year style experiment with 6-month anchor spacing was run
- Shorter evaluation horizons looked relatively stronger than longer horizons

## Objective 2 status

- Signal definitions were agreed for the four strategy families
- Strategy 1: adaptive band relative-position score
- Strategy 2: moving-average spread score with selection-period normalization
- Strategy 3: adaptive volatility-band relative-position score
- Strategy 4: fear-greed event score in `{-1, 0, 1}`

## Folder policy

- Use `docs/notes/` for raw thinking and decision logs
- Use `docs/reports/` for cleaner summaries and draft writeups
- Keep Markdown as the main editable format
