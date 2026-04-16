# Presentation Outline

Date: 2026-04-14

## Why `docs/slides`

This folder is a good place to manage presentation drafts because:

- slide planning is different from rough notes
- it is more temporary and structural than a full report
- it can later be converted into PowerPoint, Beamer, or PDF

For now, this file is the working slide outline for a `15-minute` presentation.

## Recommended Length

- First draft: `10` slides
- Expanded version: `15-20` slides if needed

The idea is to first build a clean 10-slide story, then decide which technical or mathematical slides should be added.

## Draft 10-Slide Structure

### Slide 1. Title

- Project title
- Name
- Course or context
- One-sentence summary:
  - strategy-space construction, forward validation, and practical tranche simulation on gold

### Slide 2. Motivation

- Why a single trading rule is not enough
- Why combining or reinterpreting strategies matters
- Main question:
  - can strategy outputs be treated as a predictive numerical space?

### Slide 3. Core Idea

- Expand the meaning of vectors:
  - from numbers
  - to functions
  - to strategy functions
- Build a design matrix from strategy scores
- Study future return prediction in that strategy space

### Slide 4. Objective 1

- Representative parameter selection from four strategy families
- Return matrix construction
- Weight optimization under constraints
- Signed versus long-only comparison

### Slide 5. Objective 2

- Convert strategy outputs into scores
- Build signal matrix `A`
- Predict future cumulative returns over different horizons
- Compare linear models

### Slide 6. Expanded Strategy Space

- Top 10 candidates from each strategy family
- Total of 40 basis columns
- Why this is similar to basis expansion in model selection
- Interpret this as a strategy-space analogue of function-space modeling

### Slide 7. Forward Validation

- Anchor-date setup
- Selection period versus future evaluation period
- Why this is stronger than only in-sample fitting
- Highlight that the best horizon changes across anchor dates

### Slide 8. Main Results

- Best horizon table by anchor
- OLS dominance across anchors
- `45-day` versus `120-130 day` behavior
- Mention that predictive horizon is regime-dependent

### Slide 9. Practical Simulation

- Rolling-tranche implementation
- `45-day` tranche versus `130-day` tranche
- Exposure-adjusted interpretation
- Why `45-day` often reacts faster
- Why `130-day` often behaves defensively

### Slide 10. Conclusion and Next Work

- Strategy-space construction is valid
- Horizon choice is regime-dependent
- Practical deployment requires slow model updating plus daily execution
- Future work:
  - monthly anchor updates
  - multi-asset expansion
  - sentiment/noise integration

## Possible Extra Slides for a 15-20 Slide Version

If we expand later, these are the most natural additions.

### Extra A. Mathematical Definition of the Matrix

- Explain that columns are strategy basis functions
- rows are evaluated market states
- entries are numerical values of basis functions

### Extra B. OLS / Normal Equation

- Show `A beta ≈ y`
- Explain why this counts as machine learning
- Briefly connect to model selection

### Extra C. Selection Criteria

- correlation
- directional accuracy
- AIC / BIC / cross-validation

### Extra D. Why 45 Days Sometimes Wins

- transition capture
- faster adaptation
- better for sideways-to-up shifts

### Extra E. Why 130 Days Sometimes Wins

- slower drift
- confirmation behavior
- defensive exposure control

### Extra F. Limitations

- regime dependence
- target degeneracy at long horizons
- need for faster risk overlay

### Extra G. Multi-Asset Vision

- gold as first research asset
- next steps to oil, copper, equities, bonds, FX, and crypto

## Suggested Next Step

The next presentation task should be:

1. lock the 10-slide version
2. decide which 3-5 technical slides to add
3. convert the outline into full slide text
