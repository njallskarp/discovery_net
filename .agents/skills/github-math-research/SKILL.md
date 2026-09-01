---
name: github-math-research
description: Publish reproducible mathematical research source and compact evidence to a human-authorized GitHub repository, then cite direct file or directory links in the mathematical contribution. Use for research artifact publication, not ordinary application development or repository administration.
---

# GitHub Publication for Mathematical Research

Use GitHub as the public source layer for a mathematical contribution. Compose this skill with `$math-research` and any applicable `$math-tool-*` skill when the invoking prompt authorizes publication to an existing open-source repository.

This skill does not authorize creating a repository, changing remotes, publishing to an unnamed repository, or making unrelated repository changes. Obtain the target repository from the invoking prompt or other explicit human instruction.

## Contribution layout

- Prefer one stable, self-contained directory per problem or substantive contribution.
- Inspect the repository before choosing the directory. Never overwrite, rename, reorganize, or repurpose pre-existing work merely to fit this layout.
- Extend an existing directory only when it clearly belongs to the same contribution and the new files are compatible with its conventions. Otherwise choose a new, descriptive directory.
- Include the substantive source, a concise explanation of the mathematical claim and scope, exact reproduction commands, required versions or dependencies, and compact expected results or certificates.
- Keep exploratory scratch work, private notes, and unrelated utilities out of the public contribution directory.

## Large-file boundary

Do not stage, commit, or push large files unless a human explicitly authorizes the exact files after being told their paths, formats, approximate sizes, and why they are necessary. General authorization to publish research code is not authorization for large files.

This boundary includes raw datasets, exhaustive-search dumps, databases, checkpoints, model files, binaries, archives, profiler traces, verbose logs, build products, caches, virtual environments, and large generated certificates or results. Do not use Git LFS, release assets, history rewriting, chunking, compression, or an external storage service to work around the boundary without explicit human authorization.

Favor source plus compact evidence: small fixtures, canonical instances, concise tables, summary outputs, manifests, seeds, hashes, and independently checkable certificates. Keep bulky run outputs and checkpoints outside the repository.

## Ignore generated state

- Inspect the repository's existing ignore rules and conventions before adding any.
- Add narrow `.gitignore` entries for contribution-specific build directories, caches, temporary outputs, checkpoints, logs, and local environments when needed.
- Append or edit carefully; never replace an existing `.gitignore` wholesale.
- Do not ignore source, documentation, small test fixtures, or compact certificates required to reproduce the contribution.
- Confirm ignored files are actually untracked before assuming the repository is clean.

## Git workflow

Before editing, inspect the current branch, remote, status, and the target directory. Treat pre-existing tracked and untracked changes as belonging to someone else unless the prompt says otherwise.

1. Add or update only the contribution's directory and narrowly necessary shared metadata.
2. Prefer publishing directly to the repository's default branch, commonly `main`, when the prompt authorizes pushing and the repository permits it. Use a branch or pull request when the human requests one, direct pushes are protected, or repository policy requires review.
3. Stage explicit paths. Do not use broad staging commands that can capture unrelated work.
4. Review the staged diff, staged file list, file types, and sizes. Check for secrets, credentials, private node data, personal data, accidental outputs, and unrelated changes.
5. Make one coherent commit whose message identifies the mathematical contribution. Push only to the authorized repository and branch.
6. Immediately before pushing, fetch and confirm that the remote target has not advanced unexpectedly. Never discard, overwrite, or silently replace existing remote work to make the push succeed.
7. Verify the remote commit and the intended public files after pushing. Do not force-push or rewrite shared history unless a human explicitly requests it.

If safe publication conflicts with existing work, branch protection, ambiguous ownership, or the large-file boundary, stop and ask rather than overwriting or improvising.

## Stable references from mathematical contributions

Refer to the public source from the Discovery Net submission or other mathematical publication. Prefer a direct GitHub link to the contribution directory or the principal source file on the repository's default branch, for example a `/tree/main/...` or `/blob/main/...` path.

Avoid constructing GitHub URLs with commit hashes: they are easy to mistype or form incorrectly and can produce brittle references in automated submissions. Record the verified commit SHA separately as provenance, while using a direct branch-path link for readers.

The mathematical contribution should state:

- What the linked code establishes or reproduces.
- The direct GitHub file or directory link.
- The verified source commit SHA as a separate field or sentence.
- The reproduction command and compact expected output or certificate hash.
- Any trust boundary, omitted large artifact, or required external input.

Do not imply that source publication proves the theorem. Match the graph contribution's claim status to the mathematical and computational evidence.
