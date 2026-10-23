# Contributing

This repository follows the group's branching and review rules in geg-ops,
[`computing/code/branching-and-review.md`](https://github.com/GEG-ETHZ/geg-ops/blob/main/computing/code/branching-and-review.md).
What they mean here:

## Branches

| Type | Branch | Purpose |
|---|---|---|
| Persistent | `main` | Production-ready, the default branch, protected |
| Topic | `<type>/<description>` | One change, e.g. `feat/title-fallback`, `fix/doi-suffix`, `docs/missing-papers` |

`<type>` is the Conventional Commits type of the change (`feat`, `fix`, `docs`, `refactor`, `test`,
`chore`, `perf`, `ci`), `<description>` is short kebab-case. Commits use the same form with a scope:
`fix(naming): keep the DOI suffix`.

There is no `develop` branch. The group adds one only where changes can be tested in a development
setting before they reach production. Here the function and the agent are deployed into
`geg-core-dev`, and there is no second deployment to test in.

## Merging

1. Branch from `main`, open a pull request against `main`.
2. Someone other than the author reviews it. One approval is required.
3. `just check` passes and the branch is up to date with `main`.
4. The pull request is squash-merged and the branch deleted.
5. Nobody pushes to `main` directly. Coding assistants do not push; a person does.

A change to `src/ingestor/` or `terraform/` reaches production only through `just tf-apply`, one to
`src/agent/` only through `just agent-deploy`. Say in the pull request whether it was deployed.

## When to add `develop`

Add it when there is a separate place to try a change before production, for example a second
function, corpus and agent for testing. An admin of the repository then, by hand:

1. Creates `develop` from `main` and pushes it.
2. Protects it: restrict deletions, block force pushes.
3. Keeps `main` as the default branch.
4. Updates this file and the README so pull requests target `develop`.

From then on `develop` merges into `main` with a merge commit, through a reviewed pull request.
