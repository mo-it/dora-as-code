# Invalid results, retained as evidence

Files here are measurement artefacts that were produced but must not be used as
findings. They are kept rather than deleted because the way they failed is
itself a documented result in the dissertation.

## detection-sweep-INVALID.txt

**Do not cite this file.** The valid detection-accuracy evidence is
`results/sweep-kyverno.txt`, `results/sweep-kyverno-fp.txt` and
`results/sweep-gatekeeper.txt`.

This file contains three sections labelled `baseline`, `kyverno` and
`gatekeeper`. All three are byte-for-byte identical: 20 denials and 1
admission in each.

The `baseline` section is the problem. Baseline means neither engine is
validating, so every manifest should be admitted. The isolation script states
this expectation explicitly:

    baseline)   echo "   EXPECTED for '$MODE': ADMITTED" ;;

A baseline that denies 20 violations is therefore impossible if isolation was
in effect. Two readings fit the evidence, and the surviving records do not
distinguish between them:

1. All three sections were captured with both engines live, and the section
   labels record the intended configuration rather than the actual one.
2. Isolation was applied but silently failed, so all three runs measured the
   same fully-enforcing cluster.

Either way the output is constant regardless of the configuration under test,
which is the same signature as the controller-path defect recorded as
Finding 1: an instrument that returns the same answer whatever the input is
not measuring accurately or inaccurately, it is not measuring at all.

The valid sweeps were captured separately, one engine at a time, each gated by
a behavioural probe before recording, and each is labelled with the isolation
state that produced it (for example `=== GATEKEEPER ONLY (Kyverno on Audit) ===`).

Retained 22 August 2026 during the pre-submission repository audit.
