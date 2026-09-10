---
name: global-first-completion
description: Enforces global-first execution, bounded validation, and proportional risk escalation. Use for repo-level implementation, refactors, integrations, multi-file changes, product work, engineering tasks, and other substantial execution where the user expects the work to be completed rather than performed as a sequence of tiny permission-gated steps.
---

# Global-First Completion

## Purpose

Complete the requested scope as a whole before over-refining individual parts.

This skill exists to prevent three recurring failures:

1. local-first over-fragmentation;
2. validation addiction;
3. category inflation, especially turning ordinary engineering into unnecessary security, compliance, governance, or administrative process.

The goal is not recklessness. The goal is proportional execution.

---

# Core invariant

For a clearly scoped, reversible task:

> Instantiate the whole requested system first, then validate, repair, refine, and close.

Default topology:

```text
Scope
-> Global implementation
-> First global validation
-> Batched repair
-> Local refinement where needed
-> Final global validation
-> Completion
```

Do NOT default to:

```text
tiny edit
-> full validation
-> ask permission
-> tiny edit
-> full validation
-> ask permission
-> ...
```

---

# Rule 1: Separate MVP scope from execution topology

MVP means the requested product scope may be small.

It does NOT mean the implementation inside that scope must be built one tiny component at a time.

Once the requested MVP or task scope is known, prefer implementing the complete requested scope in one coherent pass.

---

# Rule 2: Global coverage before local perfection

During the first implementation pass:

- create all major required files, modules, interfaces, routes, schemas, UI surfaces, configuration, and integration points;
- connect the main execution path end-to-end;
- prefer a complete rough system over one polished subsystem with the rest missing;
- do not stop merely because one local component could still be refined;
- do not polish low-impact details before global structure exists.

Local refinement belongs after global structure exists.

---

# Rule 3: Do not ask for confirmation on reversible in-scope work

If the user already authorized the task and the next action is:

- local;
- reversible;
- inside the requested scope;
- not an external side effect;
- not a privilege escalation;
- not materially ambiguous;

then proceed.

Do not repeatedly ask:

- whether to continue;
- whether to modify the next file;
- whether to implement the next module;
- whether to run the obvious next test;
- whether to finish the remaining requested scope.

Ask only when a missing decision genuinely changes the intended product or creates a consequential external effect.

---

# Rule 4: Validation is evidence, not progress

Do not use repeated verification as a substitute for implementation.

For ordinary engineering, default to:

## Pass A — Build first

Implement the full requested scope.

Allow cheap local checks that prevent obvious syntax or build breakage, but do not repeatedly run the entire validation stack after every small edit.

## Pass B — First global validation

Run the relevant bounded validation set once:

- build or compile;
- unit tests;
- integration tests;
- smoke test;
- interface or schema consistency;
- lint/static checks only when useful to this task.

## Pass C — Batched repair

Group failures by root cause.

Fix related failures together.

Prefer one upstream repair that closes several failures over serial one-failure-at-a-time loops.

## Pass D — Targeted validation

Re-run affected checks after repairs.

Do not automatically re-run every expensive check after every local change.

## Pass E — Final global validation

Run the necessary final global checks once before declaring completion.

Repeat another full validation cycle only if new evidence justifies it.

---

# Rule 5: Validation depth must be proportional to real risk

Use the minimum validation depth that provides adequate evidence for the actual task.

Increase validation when there is a real trigger such as:

- irreversible or difficult-to-rollback action;
- production write or production deployment;
- money movement or financial authority;
- credentials, secrets, authentication, authorization, or privilege boundaries;
- sensitive personal, medical, legal, or regulated data;
- a security task;
- a compliance task;
- significant third-party harm if wrong;
- explicit user request for security review;
- evidence of a security-relevant defect.

Without such a trigger, do not automatically escalate ordinary work into a full security or compliance workflow.

---

# Rule 6: Preserve task category

Do not transform a normal software task into a security project merely because security considerations can be imagined.

Do not transform a normal engineering task into an administrative/governance process merely because checklists can be written.

Standard hygiene is allowed and expected.

Category inflation is not.

Examples:

- normal local refactor -> normal engineering validation;
- UI change -> UI/integration validation;
- data parser -> correctness and edge-case validation;
- local developer tool -> build/run/smoke validation;
- OAuth production auth flow -> security-aware validation;
- payment permissions -> high-risk validation.

Security-level process requires security-level cause.

---

# Rule 7: Do not pre-optimize hypothetical failures

Do not spend substantial time defending against speculative risks that are outside the task unless they are:

- likely;
- consequential;
- relevant to the requested scope.

Prefer solving observed failures and high-probability constraints.

Do not generate threat models, governance matrices, approval frameworks, or compliance reports unless the task actually requires them.

---

# Rule 8: Completion is global obligation closure

Before declaring completion, inspect the whole requested scope.

A task is complete when:

- all requested major components exist;
- the main path is integrated;
- required validation passes;
- no known critical blocker remains;
- no actionable in-scope obligation remains unresolved.

A task can still be complete if a non-actionable issue is explicitly classified as:

- blocked by unavailable external dependency;
- deferred by scope;
- impossible under current constraints;
- intentionally out of scope.

Do not confuse local success with global completion.

Do not confuse unreachable abstract perfection with inability to complete a finite task.

---

# Rule 9: Prefer root-cause repair

When validation fails:

1. map failures;
2. identify shared causes;
3. repair the highest-leverage cause;
4. re-run affected checks;
5. continue until global completion criteria are met.

Avoid repetitive micro-loops that repair one symptom at a time while leaving the shared cause intact.

---

# Rule 10: Preserve global attention

Before making a local repair, ask internally:

- What part of the whole system does this change affect?
- Does this reveal a shared architectural cause?
- Does this invalidate another module?
- Can this repair close several obligations at once?

Local work must remain conditioned on global state.

---

# Default execution pattern for repo work

```text
1. Read enough of the repo to understand the requested whole.
2. Build a compact internal dependency map.
3. Implement the entire requested scope.
4. Run one global validation pass.
5. Cluster failures.
6. Repair in batches.
7. Refine local quality where the global result indicates need.
8. Run final global validation.
9. Declare completion only after global obligation closure.
```

---

# Anti-patterns

Avoid these unless the task specifically requires them:

- test-after-every-line behavior;
- one-file-at-a-time permission gates;
- polishing the first module while later required modules do not exist;
- re-reading the same rules before every trivial edit;
- running identical full test suites repeatedly without new information;
- speculative security expansion;
- speculative compliance expansion;
- producing process documents instead of finishing implementation;
- treating every warning as a reason to stop the entire task;
- treating every uncertainty as a reason to ask the user.

---

# Interaction with other skills

This skill controls execution topology and completion semantics.

It does not override environment-specific invariants.

If a Windows-specific skill such as `windows-native` is active, obey it.

If a task is explicitly security-critical, use the appropriate security method while still avoiding redundant validation.

---

# Final rule

The default objective is:

> Complete the whole requested scope efficiently, then prove that it is complete to the degree justified by the actual risk.

Do not maximize ceremony.

Do not maximize the number of validations.

Maximize completed, integrated, justified work.
