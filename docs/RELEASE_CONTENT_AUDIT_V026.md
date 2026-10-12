# v0.26.0 release-content audit

October 12, 2026. Scope: 191 changed paths against v0.25.0, including 134 docs paths, 117 historical evidence artifacts, 16 core Python paths, 15 scripts and 21 tests. This is a targeted source/evidence review, not an independent legal or penetration-test certification.

Release-input scanning and additional high-risk pattern checks detected no obvious credentials or private keys. Several historical evidence receipts contain ephemeral workstation paths, preserved for provenance; therefore do not call the archive free of personal metadata. Public historical hidden tests cannot serve as new blind benchmarks.

Third-party historical code references include PySnooper (MIT), more-itertools (MIT) and youtube-dl (Unlicense). PySnooper's copyright and full MIT notice accompany this release in THIRD_PARTY_NOTICES.md and THIRD_PARTY_PYSNOOPER_LICENSE.txt. Ignored upstream checkout trees are not bundled.

The reviewed patch/executor/cache code has explicit approval, bounded paths and constrained Docker defaults, but none are certified adversarial isolation. Passing six OS/Python CI matrix checks demonstrates release workflow compatibility, not general coding-agent performance.

Verdict: no known leaked key or proved release-blocking code-execution bypass in inspected source. External legal/privacy assurance and fresh blind evaluation remain out of scope; all negative benchmark results retained.
