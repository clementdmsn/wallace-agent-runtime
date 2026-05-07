# Analyze Project Structure

## Purpose
Identify and describe the directory layout, key files, and organizational patterns of a software project.

## Steps
1. Ensure the `path` input is provided as a relative sandbox path (for example `src`, `app`, or `.`).
2. Use `run_shell` with one safe command at a time. Do not use `cd`, pipes, redirects, or shell control operators.
3. Start with `ls -la {path}` to verify the target and inspect top-level entries.
4. Use `find {path} -maxdepth 2 -type d` to list nearby directories.
5. Use `find {path} -maxdepth 2 -type f` to list nearby files.
6. Identify common project patterns: source code, configuration, tests, documentation, assets, package manifests, and lockfiles.
7. Infer language usage from file extensions such as `.py`, `.js`, `.ts`, `.json`, `.toml`, `.md`, `.yaml`, and `.yml`.
8. Summarize the overall architecture and suggest practical next inspection steps.

## Precondition
- The provided path must exist and be accessible.

## Tools Required
- run_shell

## What to Do if Missing
If `run_shell` reports that the specified path does not exist, return `Path not found: {path}`. If no files are listed, state that the directory is empty or contains only directories within the inspected depth.
