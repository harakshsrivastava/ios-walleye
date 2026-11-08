# Recovery status

## Inventory

The accessible workspace and mounted directories were searched for the named archives, project directory, Git repositories, and reported component filenames. No original project file or archive survived. The expected feasibility archive and its expected SHA-256 could therefore not be verified or extracted. The authorized GitHub installation contained no repository matching `ios-walleye`.

## Classification

- Recovered original project files: none.
- Reconstructed in this snapshot: this status report, the machine-readable provenance manifest, precompiled-artifact report, and manifest regression tests.
- Verified external evidence: current public GitHub repository metadata, workflow definition, workflow run and artifact metadata, and the downloaded run-94 artifact/kernel hashes and Mach-O inspection.
- Historical-only evidence: hardware/FDT results, 152-test result, three assembly-object hashes, patch-application result, and Linux build blockers supplied in the recovery record. Original artifacts were unavailable, so these were not rerun or promoted to current results.
- Unavailable: original boot/DTBO/FDT/AVB/memory/ELF/Mach-O/handoff tools and reports; raw evidence; prior Git history; prior ZIPs; original test suite.

## Safety and scope

No physical device was accessed, modified, flashed, or booted. No loader address or Pixel 2 compatibility is inferred. The available `SWEET` kernel targets the upstream Redmi-oriented platform and is reference-only.

## Current regression result

The reconstructed preservation layer has four standard-library `unittest` checks covering manifest parsing, immutable commit identifiers, historical-claim labeling, and exclusion of raw device artifacts. All four passed on 2026-11-08. The original reported 152-test suite was unavailable and was not rerun.

