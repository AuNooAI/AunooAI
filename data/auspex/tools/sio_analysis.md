---
name: "sio_analysis"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Deep analysis of events with cross-verification and confidence assessment"

parameters:
  - name: event
    type: object
    required: true
    description: "Event cluster to analyze"
  - name: verify_claims
    type: boolean
    default: true
    description: "Cross-reference claims across sources"
  - name: check_contradictions
    type: boolean
    default: true
    description: "Flag contradicting claims"

output:
  type: object
  properties:
    event:
      type: object
      description: "Original event with analysis"
    claims:
      type: array
      description: "Extracted claims with sources"
    confidence_score:
      type: number
      description: "Overall confidence (0-1)"
    confidence_level:
      type: string
      description: "high/medium/low"
    contradictions:
      type: array
      description: "Identified contradictions"
    verification_status:
      type: string
      description: "verified/partial/unverified"

triggers:
  - patterns: ["analyze.*event", "verify.*claims", "deep.*analysis"]
    priority: medium
  - patterns: ["check.*credibility", "cross.*reference"]
    priority: low
---

# SIO Deep Analysis Tool

## Purpose
Perform deep analysis on individual events including claim extraction, cross-verification, and confidence assessment.

## Analysis Components

### Claim Extraction
- Extract key claims from each article
- Track source and credibility for each claim
- Identify primary and supporting claims

### Cross-Verification
- Compare claims across multiple sources
- Identify corroborating evidence
- Flag single-source claims

### Contradiction Detection
- Identify conflicting claims
- Flag sentiment mismatches
- Note timeline inconsistencies

### Confidence Calculation
Based on:
- Number of corroborating sources
- Average source credibility
- Presence of contradictions
- Claim specificity

## Confidence Levels

| Level | Score | Meaning |
|-------|-------|---------|
| HIGH | 0.85+ | Multiple credible sources agree |
| MEDIUM | 0.70-0.84 | Partial verification |
| LOW | <0.70 | Single source or contradictions |

## Returns
- Enhanced event with analysis metadata
- Extracted claims with attributions
- Confidence assessment with explanation
- List of contradictions if found
