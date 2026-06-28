# Database Modeling

Purpose: Enforce robust data structure modeling, normalizing schemas to protect consistency and applying deliberate denormalization for scale.

## Core Rules

1. Define Proper Keys and Constraints
   - Every table must have a primary key and appropriate unique constraints where logical.
   - Use foreign key constraints to guarantee referential integrity unless building high-volume distributed tables with explicit design justification.

2. Normalization Standard
   - Normalize database design to Third Normal Form (3NF) to eliminate data redundancy.
   - Only deviate from 3NF (denormalizing) when performance benchmarks prove a bottleneck, documenting the redundancy mitigation strategy.

3. Type Precision
   - Choose the most specific data type (e.g., `UUID` over string, `INT` vs `BIGINT`, exact numeric `NUMERIC` for financial figures instead of float/double).
