# Finding 1: the controller-path defect, reproduced offline

Seven Gatekeeper ConstraintTemplates read container fields at `spec.containers` while their Constraints matched controller kinds. On a controller the containers are at `spec.template.spec.containers`, so the path does not exist. Rego iteration over a missing path binds nothing, the rule body never executes, and the template reports no violation without raising an error.

The table below evaluates both template versions against identical inputs. The column that matters is whether the compliant and violating counts DIFFER: if they are equal, the policy cannot discriminate and its detection accuracy is undefined rather than merely poor.

## v1 (before the fix)

| Kind | Compliant input | Violating input | Discriminates? |
|---|---|---|---|
| Pod | 0 | 14 | YES |
| Deployment | 1 | 1 | NO -- constant output |
| StatefulSet | 1 | 1 | NO -- constant output |
| DaemonSet | 1 | 1 | NO -- constant output |
| CronJob | 1 | 1 | NO -- constant output |

## v2 (after the fix)

| Kind | Compliant input | Violating input | Discriminates? |
|---|---|---|---|
| Pod | 0 | 14 | YES |
| Deployment | 0 | 14 | YES |
| StatefulSet | 0 | 14 | YES |
| DaemonSet | 0 | 14 | YES |
| CronJob | 0 | 14 | YES |

## Per-template behaviour on a Deployment (v1)

| Template | Compliant | Violating | Failure mode |
|---|---|---|---|
| req006-resource-limits | 0 | 0 | Silent -- iteration binds nothing (false negatives) |
| req009-image-tag | 0 | 0 | Silent -- iteration binds nothing (false negatives) |
| req010-non-root | 0 | 0 | Silent -- iteration binds nothing (false negatives) |
| req011-privileged | 0 | 0 | Silent -- iteration binds nothing (false negatives) |
| req018-security-context | 0 | 0 | Silent -- iteration binds nothing (false negatives) |
| req019-default-sa | 1 | 1 | Always fires -- missing field defaults (false positives) |
| req023b-registries | 0 | 0 | Silent -- iteration binds nothing (false negatives) |

Six templates iterate with `collection[_]` over a path that does not exist on a controller. Iteration over a missing path binds nothing, so the body never runs and no violation is reported: false negatives, silently. One template, REQ-019, instead reads a scalar with `object.get(spec, "serviceAccountName", "default")`. On a controller that field is absent, so the fallback `"default"` is returned and the rule matches every object including compliant ones: false positives, loudly. The same authoring mistake produces opposite failures depending only on whether the rule iterates a collection or tests a scalar.

## Interpretation

Both versions behave correctly on a bare `Pod`, which is the shape used in most Gatekeeper documentation and in most tutorial examples. That is why the defect survived review: the policies were demonstrably working on the object everyone tests with, and silently inert on the objects actually deployed.
