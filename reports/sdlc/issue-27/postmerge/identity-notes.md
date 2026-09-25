# Candidate identity and reviewer runtime supplement

The independent verifier matched all 33 file digests and both deletions. Its
aggregate-preimage limitation is resolved by this exact Python serialization:

```python
payload = {"files": candidate["files"], "deleted": candidate["deleted"]}
digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
assert digest == candidate["candidate"]
```

Use Python json.dumps defaults (including spaces and ensure_ascii=True), with no
trailing newline. Main recomputed the value as
`86c59c56ab890f884849ec863ccb1de7cd4481ac64aa31ce09c7e8d7779f305a`, matching candidate.json.
This clarification changes no candidate source.

The reviewer observed model/effort in its own session metadata; permission mode
is not exposed there. Main
observed the actual reviewer process arguments and its own session metadata:
reviewer-runtime.json records grok-4.7/high from summary.json and high/auto from
process argv. Auto is supported by installed grok --help. No configuration or
permission changes were made. Explicit AK high overrides the SDLC medium default;
no default-medium gate is claimed. Exact-head PR review remains a separate step.
