# bucketgen

Smart wordlist generator for cloud bucket enumeration (S3 / GCS / Azure Blob).

`bucketgen` takes one or more target names and produces a **probability-ranked**
wordlist of likely bucket names. The most probable candidates appear first, so
when you feed the list into a resolver with rate limits, the realistic hits show
up in the first few hundred lines instead of being buried in noise.

> 🇧🇷 Versão em português: [README.md](README.md)

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

## Nuclei integration

The natural workflow is to generate the wordlist with `bucketgen` and feed it to
[Nuclei](https://github.com/projectdiscovery/nuclei)'s bucket-enumeration templates.
Those templates take the wordlist through a `wordlist` variable.

First generate the list (using `--valid-only` avoids wasting requests on invalid names):

```bash
# for GCS
python3 bucketgen.py -t example -m web --valid-only -o word.txt

# for S3
python3 bucketgen.py -t example -m web --valid-only -o buckets.txt
```

Then run the templates pointing at the file:

```bash
# GCP / Google Cloud Storage
nuclei -t ~/nuclei-templates/cloud/enum/gcp-bucket-enum.yaml -var wordlist=word.txt -esc -lfa

# AWS S3
nuclei -t ~/nuclei-templates/cloud/enum/aws-s3-bucket-enum.yaml -var wordlist=buckets.txt -esc -lfa
```

Flags used:

- `-var wordlist=FILE` — passes the generated wordlist path to the template.
- `-esc` (`-enable-self-contained`) — enables self-contained templates (the ones that
  don't need a `-u` target, like these enumeration templates).
- `-lfa` (allow local file access) — lets the template read the local wordlist file.

Tip: with `bucketgen`'s ranked output, combine with `--max` to run the most probable
candidates first and widen the net only if you get a signal:

```bash
python3 bucketgen.py -t example -m web --valid-only --max 5000 -o buckets.txt
nuclei -t ~/nuclei-templates/cloud/enum/aws-s3-bucket-enum.yaml -var wordlist=buckets.txt -esc -lfa
```

## Example pipeline

```bash
# generate, keep top 10k valid names, resolve
python3 bucketgen.py -t example google -m web --valid-only --max 10000 -o wl.txt
# then feed wl.txt into your bucket resolver of choice
```

## Nuclei integration

The generated wordlist plugs straight into the bucket-enumeration templates in
[nuclei-templates](https://github.com/projectdiscovery/nuclei-templates), which
take the list through the `wordlist` variable.

```bash
# 1) generate the wordlist (top 10k valid names is a good start)
python3 bucketgen.py -t example google -m web --valid-only --max 10000 -o buckets.txt

# 2) AWS S3
nuclei -t ~/nuclei-templates/cloud/enum/aws-s3-bucket-enum.yaml \
  -var wordlist=buckets.txt -esc -lfa

# 3) GCP Storage
nuclei -t ~/nuclei-templates/cloud/enum/gcp-bucket-enum.yaml \
  -var wordlist=buckets.txt -esc -lfa
```

Flag breakdown:

- `-t` — path to the enumeration template (S3 or GCP).
- `-var wordlist=buckets.txt` — feeds the bucketgen list into the template's
  `wordlist` variable. Use the same file for both.
- `-esc` (`-enable-self-contained`) — enables self-contained templates; the
  cloud-enum templates are code/self-contained and won't run without it.
- `-lfa` (`-allow-local-file-access`) — permits the local file access needed for
  the template to read the wordlist from disk.

> **Note:** verify the template path. In recent nuclei-templates versions the
> cloud-enum files may live under `cloud/enum/` or elsewhere — adjust `-t` to
> match your tree: `find ~/nuclei-templates -name '*bucket-enum*'`

## Legal

This tool is intended for **authorized security testing only**. Use it solely
against assets you own or are explicitly permitted to test (bug bounty scope,
signed engagement, your own infrastructure). The author is not responsible for
misuse. Always confirm scope before enumerating.

## License

MIT — see [LICENSE](LICENSE).
