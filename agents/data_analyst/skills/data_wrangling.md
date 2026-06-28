# Data Wrangling

Purpose: Standardize, restructure, and clean incoming raw data streams.

## Core Rules

1. Define a Validation Schema
   - Before parsing or transforming dataset fields, declare structural schema requirements (required columns, data types, value ranges).
   - Flag or isolate dirty rows that violate validation invariants (e.g. invalid dates, negative prices).

2. Handle Missing Values Explicitly
   - Never let missing data propagate silently. Choose a clear imputation strategy (mean/median, interpolation, constant placeholders) or filter them out, explaining the rationale.

3. Type Safety
   - Coerce columns to correct formats (e.g., parsing datetime string with strict timezone context) at the entry point of the analytics pipeline.
