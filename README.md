# bucketgen

Smart wordlist generator for cloud bucket enumeration (S3 / GCS / Azure Blob).

`bucketgen` takes one or more target names and produces a **probability-ranked**
wordlist of likely bucket names. The most probable candidates appear first, so
when you feed the list into a resolver with rate limits, the realistic hits show
up in the first few hundred lines instead of being buried in noise.

## Why

Generic permutation tools treat every term equally and combine everything with
everything, producing huge low-quality lists. `bucketgen` separates **primary**
terms (your actual target) from **complementary** terms (modifiers like regions
or product names), scores each candidate by patterns seen in real-world buckets,
and sorts the output accordingly.

## Features

- **Probability ranking** — candidates scored by how often the pattern appears
  in real buckets (`prd-`, `-backup`, `-assets` rank high; `tst-`, `demo-` low).
- **Primary vs. complementary terms** — primaries get full wordlists; modifiers
  only attach to a primary (`example-web`), never appear alone.
- **Composite affixes** — `example-api-prd`, `example-static-assets`, `prd-example-backup`.
- **AWS regions** — `sa-east-1` prioritized, plus the common US/EU regions.
- **Years** — `example-2024`, `example-backup-2023`.
- **Account-id placeholder** — emits `example-ACCOUNTID` for later `sed` substitution.
- **PT-BR functions** — `boletos`, `arquivos`, `documentos`, `notasfiscais`...
  (useful for Brazilian-scope targets that English wordlists miss).
- **External wordlist** — plug your own recon terms via `--wordlist`.
- **Interactive mode** — run with no arguments and it prompts for the essentials.
- **S3 name validation** — `--valid-only` keeps only RFC-valid bucket names.

## Requirements

Python 3.6+ (standard library only, no dependencies).

## Usage

```bash
# single primary target
python3 bucketgen.py example

# primaries (-t) + complementary modifiers (-m)
python3 bucketgen.py -t example google -m web cloud "data lake"

# cap output and keep only valid S3 names
python3 bucketgen.py -t example -m web --max 5000 --valid-only

# show scores (debug / tuning)
python3 bucketgen.py example --scores | head -30

# write to file
python3 bucketgen.py -t example google -m web -o buckets.txt

# bring your own recon terms
python3 bucketgen.py example --wordlist recon_extra.txt

# interactive mode (asks for primary + complementary terms)
python3 bucketgen.py
```

### Primary vs. complementary

| Term type | Flag | Behaviour | Example output |
|-----------|------|-----------|----------------|
| Primary | positional or `-t/--target` | full wordlist on its own | `prd-example`, `example-backup` |
| Complementary | `-m/--mod` | only attaches to a primary | `example-web`, `prd-example-web` |

A complementary term is **never** emitted by itself — no `prd-web`, no
`web-backup`. It only exists glued to a primary.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-t`, `--target` | — | Primary/target term(s). |
| `-m`, `--mod` | — | Complementary term(s); only attach to a primary. |
| `-o`, `--output` | stdout | Output file. |
| `--max N` | 0 (unlimited) | Keep only the top N ranked entries. |
| `--valid-only` | off | Keep only valid S3 bucket names. |
| `--wordlist FILE` | — | Extra affixes, one per line (`#` for comments). |
| `--scores` | off | Print the score next to each entry. |
| `--no-combine` | on | Disable combining terms. |
| `--no-composite` | on | Disable composite affixes. |
| `--no-regions` | on | Disable AWS region mutations. |
| `--no-years` | on | Disable year mutations. |
| `--no-account` | on | Disable the account-id placeholder. |
| `--no-ptbr` | on | Disable Portuguese function words. |

### Account-id placeholder

When `--no-account` is **not** set, the tool emits candidates containing the
literal string `ACCOUNTID`:

```
example-ACCOUNTID
ACCOUNTID-example
```

Once you know the real 12-digit AWS account id, substitute it across the list:

```bash
sed 's/ACCOUNTID/123456789012/g' buckets.txt > buckets-final.txt
```

## Example pipeline

```bash
# generate, keep top 10k valid names, resolve
python3 bucketgen.py -t example google -m web --valid-only --max 10000 -o wl.txt
# then feed wl.txt into your bucket resolver of choice
```

## Legal

This tool is intended for **authorized security testing only**. Use it solely
against assets you own or are explicitly permitted to test (bug bounty scope,
signed engagement, your own infrastructure). The author is not responsible for
misuse. Always confirm scope before enumerating.

## License

MIT — see [LICENSE](LICENSE).
