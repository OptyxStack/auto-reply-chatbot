# RAG_DEVELOPMENT_STRATEGY

## Purpose

This document defines the project development strategy for evolving the chatbot into the target RAG architecture described in [UPGRADE_RAG_DESIGN.md](/e:/docs/project/auto-reply-chatbot/UPGRADE_RAG_DESIGN.md).

It is not a low-level implementation spec.
It defines:

- Product and technical priorities
- Development sequencing
- Workstreams
- Rollout strategy
- Success metrics
- Governance rules for change

## Strategic Objective

The project should evolve from a functional RAG chatbot with strong safety bias into a production-grade answer system that is:

- More useful under partial evidence
- More intentional in retrieval behavior
- More explainable at every stage
- More measurable during iteration
- Safer through bounded answering, not only hard refusal

The strategic target is not "answer more at any cost".
The target is:

- Increase useful answer rate
- Reduce unnecessary clarification loops
- Preserve or improve grounding quality
- Keep escalation behavior reliable on high-risk cases

## Product Strategy

### Primary Product Outcome

The chatbot should become better at handling three realistic support states:

1. `Fully answerable`
   The system has enough evidence and should answer directly.

2. `Partially answerable`
   The system does not have perfect evidence, but can still provide a bounded, useful answer.

3. `Not safely answerable`
   The system genuinely needs clarification or human escalation.

Current behavior over-favors state 3.
The new strategy is to expand state 2 without weakening state 3.

### Product Value Priority

Feature priorities should follow this order:

1. Better answer usefulness on common support questions
2. Better consistency in pricing, policy, and troubleshooting flows
3. Lower friction from unnecessary `ASK_USER`
4. Higher operator trust through explainable decision paths
5. Lower cost through smarter model usage after logic stabilizes

The team should not optimize polishing, UI wording, or minor prompt quality ahead of evidence and routing quality.

## Technical Strategy

### Hybrid Normalizer Strategy

The normalizer should be treated as a reusable platform component, not a domain-specific rules engine.

Target operating model:

- Rule-based logic stays minimal and generic
- LLM is the primary semantic analyzer when enabled
- Deployment-specific domain behavior is restored through config, not by hard-coding domain vocabulary into core code

This changes the strategy in an important way:

- generic deployments should work with thin deterministic rules plus LLM understanding
- existing domain-heavy deployments should be supported through compatibility config

The goal is to make the normalizer portable across products while avoiding a hard break for current tenants.

### Core Engineering Principles

All changes should follow these principles:

- `Contract first`: define stable objects before rewriting logic
- `Stage isolation`: each pipeline stage should be independently testable
- `Explainability`: every stage should emit machine-readable reasons
- `Safe partial answers`: uncertainty should become bounded output, not immediate refusal
- `Measured iteration`: no major logic change without evaluation impact tracking

### Architecture Strategy

The project should be upgraded in layers, not rewritten all at once.

The recommended order is:

1. Stabilize contracts and orchestration
2. Improve query understanding
3. Improve retrieval quality and evidence construction
4. Replace rigid gating with lane-based routing
5. Upgrade post-generation verification
6. Optimize cost and polish only after behavior stabilizes

This avoids a common failure mode where prompt changes mask structural retrieval problems.

## Development Workstreams

The project should be managed as parallel but coordinated workstreams.

### Workstream 1: Contracts and Runtime State

Scope:

- Shared objects between stages
- Runtime context management
- State transitions
- Decision reason logging

Key files:

- `app/services/schemas.py`
- `app/services/orchestrator.py`

Goal:

Build a stable internal language for the pipeline so later improvements do not create fragile coupling.

Why first:

Without this, every later change becomes harder to validate and harder to integrate.

### Workstream 2: Query Understanding

Scope:

- Language handling
- Query normalization
- Intent inference
- Minimal generic slot handling
- Ambiguity classification
- LLM-first semantic interpretation
- Config-driven domain override for optional entity extraction, slots, and query expansion

Key files:

- `app/services/language_detect.py`
- `app/services/normalizer.py`

Goal:

Make the system understand what the user wants before retrieval begins.
Do this without baking one product domain into the shared normalizer.

Why important:

Bad retrieval strategy usually starts with weak query understanding.
Domain-specific logic inside the normalizer also makes reuse and rollout harder, so that logic should move into config and LLM interpretation.

### Workstream 3: Retrieval and Evidence Construction

Scope:

- Retrieval profiles
- Retry planning
- Candidate pooling
- Reranking
- Evidence set selection

Key files:

- `app/services/retrieval.py`
- `app/search/reranker.py`
- `app/services/retry_planner.py`
- `app/services/evidence_evaluator.py`

Goal:

Upgrade retrieval from "fetch top-k chunks" to "assemble the most useful evidence set for this answer".

Why important:

This is the highest-leverage quality area in the project.

### Workstream 4: Decisioning and Answer Lanes

Scope:

- Evidence sufficiency assessment
- Decision routing
- Strong vs weak answer lanes
- Clarification criteria

Key files:

- `app/services/evidence_quality.py`
- `app/services/decision_router.py`
- `app/services/answer_service.py`

Goal:

Reduce false-negative refusals while keeping bounded behavior under uncertainty.

Why important:

This is where user-perceived usefulness improves most directly.

### Workstream 5: Post-Generation Verification

Scope:

- Claim-level review
- Self-critique policy
- Lane downgrade
- Retry vs trim decisions

Key files:

- `app/services/reviewer.py`
- `app/services/self_critic.py`

Goal:

Make final answer validation more precise and less destructive.

Why important:

The current review style is too coarse and can reject useful answers.

### Workstream 6: Output Quality and Cost Control

Scope:

- Final polish boundaries
- Task-aware model routing
- Cache strategy
- Token budget controls

Key files:

- `app/services/final_polish.py`
- `app/services/llm_gateway.py`

Goal:

Improve efficiency and response quality after core behavior becomes stable.

Why later:

Cost optimization before logic stabilization usually locks in weak architecture.

## Development Sequence

### Stage 1: Foundation

Objective:

Create the internal contracts and state model that future logic will depend on.

What to build:

- New object contracts
- Central orchestrator state
- Stage reason logging
- Backward-compatible adapters

What not to optimize yet:

- Prompt wording
- Final UI response style
- Aggressive model switching

Definition of success:

- Every current step can be represented inside a stable runtime contract
- The team can trace a request through explicit stage states

### Stage 2: Make Query Understanding Reliable

Objective:

Stop deriving downstream behavior from raw keyword heuristics.

What to build:

- Hybrid `QuerySpec` generation
- Ambiguity typing
- Retrieval profile selection
- Better rewrite candidates
- Minimal deterministic fallback when LLM is off or fails
- Config switches for optional domain terms, slots, and query expansion

Definition of success:

- Retrieval behavior can be explained from `QuerySpec`
- Ambiguous vs under-specified vs answerable queries are no longer conflated
- The generic path works without hard-coded domain vocabulary
- A legacy domain deployment can recover richer behavior through config only

### Stage 3: Make Retrieval Intentional

Objective:

Increase evidence quality before touching generation.

What to build:

- Profile-based retrieval
- Distinct retry plans
- Candidate pool vs final evidence set separation
- Requirement-aware reranking

Definition of success:

- Retrieval attempts are meaningfully different across retries
- One good evidence path is not diluted by a broad but noisy top-k set

### Stage 4: Make Decisioning Useful

Objective:

Turn evidence quality into user value instead of rigid refusals.

What to build:

- `PASS_WEAK`
- Evidence sufficiency logic
- Answer planning
- Boundaries for partial answers

Definition of success:

- Useful answer rate rises
- Unnecessary `ASK_USER` drops
- Unsupported confident answers do not increase

### Stage 5: Tighten Review Precision

Objective:

Audit what the model said, not only how many citations it returned.

What to build:

- Claim segmentation
- Claim-to-evidence mapping
- Trim/downgrade logic
- Targeted retry only when likely beneficial

Definition of success:

- Fewer valid answers are rejected
- Unsupported claims are isolated instead of causing whole-response failure

### Stage 6: Optimize Quality and Cost

Objective:

Improve efficiency and presentation after core behavior is proven.

What to build:

- Task-aware LLM routing
- Per-task cache policy
- Controlled final polish
- Cost-aware model policy

Definition of success:

- Lower cost per useful answer
- No regression in grounding or lane behavior

## Delivery Strategy

### Iteration Model

Development should run in short, behavior-focused cycles.

Recommended cycle:

1. Choose one workstream and one measurable outcome
2. Implement behind feature flags or adapters
3. Evaluate with fixed test cases
4. Compare metrics to baseline
5. Keep, revise, or rollback based on observed behavior

The team should avoid mixing major changes to:

- Retrieval strategy
- Routing policy
- Prompt format
- Reviewer logic

in one release batch.

If multiple of these change together, regressions will be hard to attribute.

### Release Unit

Each release should ship one of the following units:

- Contract foundation release
- Normalizer decoupling release
- Retrieval behavior release
- Routing behavior release
- Review behavior release
- Cost optimization release

Do not package a major behavior release with unrelated UI or deployment changes if the goal is to observe answer-quality movement.

## Evaluation Strategy

### Primary Metrics

The project should be judged by outcome metrics, not only code completion.

Core metrics:

- `Useful answer rate`
  Percentage of responses that provide actionable value to the user

- `Unnecessary ask rate`
  Percentage of cases where the system asks for clarification but could have answered partially or fully

- `Grounded answer rate`
  Percentage of answers whose claims are supported by selected evidence

- `Unsupported confident answer rate`
  Percentage of answers that overstate beyond evidence

- `High-risk escalation precision`
  Percentage of high-risk cases escalated appropriately

- `Retry effectiveness`
  Percentage of retries that materially improve evidence sufficiency

### Secondary Metrics

- Cost per useful answer
- Average attempts per query
- Evidence coverage by intent type
- Weak-answer conversion rate
- Claim trim rate in reviewer

### Evaluation Dataset Strategy

The project should maintain a stable evaluation set with realistic support cases.

Minimum categories:

- Pricing / order link questions
- Refund / policy questions
- Setup / how-to questions
- Product comparison questions
- Ambiguous follow-up questions
- Under-specified but still answerable questions

The same eval set should be used across phases so the team can measure direction, not only isolated gains.

## Rollout Strategy

### Controlled Rollout

New behavior should be released progressively.

Recommended progression:

1. Internal developer testing
2. Offline evaluation against benchmark cases
3. Shadow mode or decision logging only
4. Partial live enablement for selected lanes or intents
5. Wider production rollout after metric confirmation

### Feature Flag Strategy

Behavioral upgrades should be isolated behind flags or selectors such as:

- new contracts enabled
- hybrid normalizer enabled
- normalizer domain terms enabled
- normalizer slots enabled
- normalizer query expansion enabled
- retrieval profile engine enabled
- evidence set builder enabled
- weak-answer lane enabled
- claim-level reviewer enabled
- task-aware gateway enabled

This allows selective rollback of specific stages without discarding the entire upgrade path.

### Rollback Rule

Any new stage behavior should be rolled back if it causes one of the following:

- clear increase in unsupported confident answers
- strong drop in grounded answer quality
- retry loops growing without usefulness improvement
- weak-answer lane becoming vague or misleading

Rollback should target the specific stage or feature flag, not the whole project direction.

### Compatibility Rollout for Hybrid Normalizer

The normalizer should be rolled out in two compatibility bands:

1. `Generic default`
   No domain terms, no rule-based slot extraction, no forced keyword expansion.
2. `Legacy compatibility`
   Domain terms, slots, and query expansion restored only through explicit config.

This lets the team validate that the shared normalizer remains generic while existing deployments keep stable behavior.

## Prioritization Rules

When choosing what to build next, prioritize in this order:

1. Changes that remove hard-coded domain assumptions from shared logic
2. Changes that improve retrieval correctness
3. Changes that reduce false-negative gating
4. Changes that improve review precision
5. Changes that improve observability
6. Changes that reduce cost
7. Changes that improve final wording

This order should be enforced consistently.
Otherwise the team risks spending time on polished output generated from weak evidence.

## Governance Rules

### Change Acceptance Rule

A behavior-changing change should only be accepted if:

- It has a clearly stated target metric
- It can be isolated to one or two pipeline stages
- It has evaluation evidence against baseline
- It does not materially worsen unsupported confident answers

### Design Consistency Rule

Any new logic added to the project should align with the target architecture:

- Query understanding should not be duplicated in multiple later stages
- The shared normalizer should not re-accumulate hard-coded domain vocab when config or LLM can supply it
- Retrieval should not reintroduce broad keyword heuristics if profile logic exists
- Review should not revert to coarse citation-count logic once claim-level review is in place
- Final polish should not be used to hide weak evidence or weak routing

### Documentation Rule

Each major phase should update:

- design assumptions
- object contracts
- active feature flags
- evaluation outcomes
- known tradeoffs

This keeps the project operable as the architecture evolves.

## Team Execution Model

Even for a small team, execution should conceptually follow these roles:

- `Architecture owner`
  Maintains contracts, boundaries, and long-term consistency

- `Retrieval owner`
  Owns candidate generation, reranking, evidence selection, and retry quality

- `Decisioning owner`
  Owns sufficiency logic, routing, and answer-lane policy

- `Evaluation owner`
  Owns benchmark sets, metrics, and regression detection

One person may cover multiple roles, but the responsibilities should stay distinct.

## Major Risks and Strategy Response

### Risk 1: Over-correction into higher hallucination

If the project only tries to reduce `ASK_USER`, it may begin answering beyond evidence.

Strategic response:

- Use `PASS_WEAK` as a bounded lane
- Keep claim-level review strict
- Track unsupported confident answer rate as a stop metric

### Risk 2: Complexity without observability

A smarter pipeline can become opaque and difficult to debug.

Strategic response:

- Require structured stage outputs
- Log stage reasons and lane decisions
- Keep object contracts explicit and versionable

### Risk 3: Premature optimization

The team may optimize token cost or prompt quality before fixing retrieval and routing.

Strategic response:

- Enforce prioritization rules
- Treat cost optimization as a late-stage stream

### Risk 4: Large-batch rewrites

Changing too many behavior layers at once makes regressions untraceable.

Strategic response:

- Ship by workstream
- Ship behind flags
- Evaluate against fixed benchmark sets

## Strategic Milestones

The project should aim for these milestone states:

### Milestone A: Observable Pipeline

The team can explain what every stage decided and why.

### Milestone B: Intentional Retrieval

Retrieval behavior is driven by `QuerySpec` and `RetrievalPlan`, not broad keyword inference.

### Milestone C: Safe Partial Answers

The system can deliver bounded useful answers when evidence is incomplete.

### Milestone D: Precision Review

The reviewer can isolate unsupported claims instead of rejecting entire answers.

### Milestone E: Efficient Production Behavior

The project maintains quality while using model budget intentionally and predictably.

## Definition of Strategic Success

The strategy is successful when the project reaches a state where:

- Retrieval is clearly better targeted by intent
- The system answers more useful cases without becoming more speculative
- Clarification is used only when it is genuinely needed
- High-risk cases remain reliably contained
- Changes can be rolled out, measured, and reversed by stage

At that point, the project will have moved from a feature-rich prototype into a controllable RAG platform that can continue evolving safely.

