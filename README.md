# riggit

riggit is a command-line tool for enforcing and auditing commit-message conventions.
It validates commit messages against a Conventional Commits-style format, supports per-repository and global configuration, and can install a git commit-msg hook so checks run automatically during commits.

## Installation

From a local checkout:

```bash
python -m pip install -e .
```

To verify the CLI is available:

```bash
riggit --help
```

## Quick start

1. Create a configuration file for the current repository:

   ```bash
   riggit init
   ```

2. Lint a message directly:

   ```bash
   riggit lint -m "feat: add search"
   ```

3. Install the commit-msg hook to enforce checks during commit:

   ```bash
   riggit install
   ```
## overview

## Command reference

### lint

Validate a commit message against the active convention.

To lint the last commit message (HEAD):

```bash
riggit lint
```

Can alter the format of the lint output (default is text, alternative is json):
```bash
riggit lint --format json
```

To lint inline messages or read from a text file:
```bash
riggit lint -m "fix(api): handle timeout"
riggit lint --message-file example.txt
```

Options:
- `--message` / `-m`: validate inline message
- `--message-file`: read the message from a file
- `--repo PATH`: operate on a different repository
- `--format text|json`: choose text or JSON output

If no message is supplied, riggit uses the last commit message.

### install / uninstall

Install or remove a git commit-msg hook that runs riggit automatically.

```bash
riggit install
riggit uninstall
```

The installed hook will mean that when a commit is attempted the message is linted and the commit only proceeds if the message is 'valid'.

Use `--force` to overwrite an existing hook file.

### init

Create a default `.riggitrc` file in the current repository.

```bash
riggit init
riggit init --force
```
`.riggitrc` files are discussed in more detail later

### scan

Inspect a range of git history and report commits that violate the convention.

```bash
riggit scan
riggit scan --since HEAD~10 --until HEAD
riggit scan --fix --force
```

Use `--fix` to attempt simple automatic rewrites such as lowercasing the description or removing a trailing period. 

The `--force` flag applies the rewrite to history.

### stats

Summarize commit quality over a commit range.

```bash
riggit stats
riggit stats --since HEAD~20 --until HEAD --format json
```

The output includes:
- total commits analyzed
- percent compliant
- most common violations
- compliance by author

### hook

Print the hook script or install it in a global or template location.

```bash
riggit hook
riggit hook --install --global
riggit hook --install --template
riggit hook --uninstall --global
```

### config

View or change configuration values.

To view current config:

```bash
riggit config --list
riggit config types
```

To alter config values:
```bash
riggit config types "feat,fix,docs,chore"
riggit config scope_required true
riggit config max_header_length 120
riggit config description_case any
riggit config no_trailing_period false
```

Allows you to edit local or global configuration (stored in .riggitrc) of conventional commits without diving into file

Use `--global` to edit the global config instead of the local repository config.

### branch

Show the current branch name and optionally extract a ticket/issue key.

```bash
riggit branch
riggit branch --extract
riggit branch --extract --format "^([A-Z]+-\\d+)"
```

### commit

A thin wrapper around `git commit` that validates the message before committing.

```bash
riggit commit -m "feat: add new endpoint"
riggit commit -m "fix: resolve timeout" --auto
```

With `--auto`, riggit extracts a ticket key from the current branch name and appends it as a `Refs:` footer when it is not already present.

## Configuration

riggit reads configuration from three layers, in order of precedence:

1. built-in defaults
2. global config at `~/.config/riggit/config.yaml`
3. local `.riggitrc` in the current repository (or a parent directory)

If no config file is present, riggit falls back to standard Conventional Commits-style defaults.

### Supported keys

- `types`: a list of allowed commit types
- `scope_required`: require a scope like `feat(api): ...`
- `max_header_length`: maximum header length, or `null` to disable the check
- `description_case`: `lower` to warn on capitalized descriptions, or `any` to disable that check
- `no_trailing_period`: warn when the description ends with a period

### Example `.riggitrc`

```yaml
# .riggitrc
types:
  - feat
  - fix
  - docs
  - chore
scope_required: false
max_header_length: 100
description_case: lower
no_trailing_period: true
```

## Default validation rules

The built-in convention follows the Conventional Commits structure:

```text
<type>[(scope)][!]: <description>
```

Rules enforced by default include:
- the header must be present and non-empty
- the type must be lowercase
- the type must be one of the configured allowed types
- a scope must not be empty if parentheses are used
- the description must not be empty
- the description should not end with a period (warning)
- a `BREAKING CHANGE:` footer is recognized as a breaking change marker

## Examples

Valid examples:

```bash
riggit lint -m "feat: add login flow"
riggit lint -m "fix(api): handle timeout"
riggit lint -m "docs: update installation steps"
```

Invalid examples:

```bash
riggit lint -m "Feature: add login flow"
riggit lint -m "feat:"
riggit lint -m "fix(api): Handle timeout."
```

## Further help

Use the built-in help for the latest command options:

```bash
riggit --help
riggit lint --help
riggit scan --help
```
