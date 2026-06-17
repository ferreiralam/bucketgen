#!/usr/bin/env python3
"""
bucketgen.py - Gerador inteligente de wordlists para enum de buckets (S3/GCS/Azure).

Uso:
    ./bucketgen.py example
    ./bucketgen.py -t example google -m web cloud -o buckets.txt
    ./bucketgen.py -t example -m web --max 5000 --valid-only
    ./bucketgen.py example --wordlist recon_extra.txt
    ./bucketgen.py example --no-composite --no-ptbr   # desliga features

Saida RANQUEADA por probabilidade (maior chance primeiro). Bom pra resolver
com rate limit: os hits provaveis aparecem nas primeiras centenas de linhas.

Features:
  - score de probabilidade por padroes de buckets reais
  - afixos compostos (api-prd, static-assets, prd-backup)
  - regioes AWS (foco BR: sa-east-1) + anos + placeholder de account-id
  - funcoes em PT-BR (homologacao, arquivos, boletos, documentos...)
  - combinacao entre termos, normalizacao de acentos/espacos
  - dicionario externo via --wordlist
"""

import argparse
import sys
import unicodedata
from itertools import permutations

# ====================== AFIXOS COM PESO (0-100) ======================
# peso alto = aparece muito em buckets reais -> sobe no ranking
ENVS = {
    "prd": 90, "prod": 88, "production": 60, "stg": 75, "stage": 60,
    "staging": 65, "dev": 80, "hml": 78, "homolog": 55, "homologacao": 50,
    "qa": 60, "uat": 55, "test": 70, "tst": 50, "sandbox": 45, "demo": 45,
}
FUNCS = {
    "api": 85, "cdn": 80, "static": 82, "assets": 84, "media": 75,
    "files": 78, "uploads": 80, "backup": 88, "backups": 70, "logs": 82,
    "data": 75, "app": 70, "web": 68, "img": 70, "images": 72,
    "public": 76, "private": 65, "bucket": 60, "storage": 65, "s3": 50,
}
# Funcoes PT-BR (diferencial pro escopo BR)
FUNCS_PTBR = {
    "arquivos": 60, "documentos": 58, "imagens": 55, "backups": 60,
    "boletos": 50, "notas": 48, "notasfiscais": 45, "relatorios": 45,
    "anexos": 48, "comprovantes": 42, "faturas": 45, "contratos": 42,
}
# Regioes AWS (foco BR primeiro)
REGIONS = {
    "sa-east-1": 70, "us-east-1": 65, "us-east-2": 40, "us-west-2": 45,
    "eu-west-1": 35, "saeast1": 40, "useast1": 40,
}
YEARS = {str(y): (55 - i * 6) for i, y in enumerate(range(2025, 2019, -1))}
ACCOUNT_PLACEHOLDER = {"ACCOUNTID": 40}  # usuario troca pelo account id real

SEPARATORS = ["-", ".", "_", ""]
SEP_WEIGHT = {"-": 1.0, ".": 0.85, "_": 0.6, "": 0.55}

# pesos de posicao: prefixo de ambiente e sufixo de funcao sao mais comuns
POS_ENV_PREFIX = 1.0
POS_ENV_SUFFIX = 0.7
POS_FUNC_PREFIX = 0.75
POS_FUNC_SUFFIX = 1.0


def normalize(term: str) -> str:
    t = unicodedata.normalize("NFKD", term)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().strip()


def space_variants(term: str):
    t = normalize(term)
    if " " not in t:
        return {t}
    parts = t.split()
    return {sep.join(parts) for sep in SEPARATORS}


def build_bases(targets, mods, combine):
    """
    Gera as bases que receberao afixos.

    - targets (primarios): cada um vira base completa, score maximo.
    - mods (complementares): NUNCA viram base sozinhos. So existem
      anexados a um primario (target + mod), e tambem combinam entre
      primarios (target + target).
    """
    bases = {}  # base -> score-base
    t_exp = []  # variacoes de espaco de cada primario
    for term in targets:
        v = space_variants(term)
        t_exp.append(v)
        for b in v:
            bases[b] = max(bases.get(b, 0), 100)  # primario puro = topo

    m_exp = [space_variants(m) for m in mods]  # complementares

    if combine:
        t_reps = [sorted(v)[0] for v in t_exp]
        m_reps = [sorted(v)[0] for v in m_exp]

        # 1) primario + complementar (example-web, google-cloud)
        #    so nessa ordem: alvo primeiro, modificador depois
        for tr in t_reps:
            for mr in m_reps:
                for sep in SEPARATORS:
                    name = f"{tr}{sep}{mr}"
                    bases[name] = max(bases.get(name, 0), 80 * SEP_WEIGHT[sep])

        # 2) primario + primario (example-google) - ambas ordens
        if len(t_reps) > 1:
            for combo in permutations(t_reps, 2):
                for sep in SEPARATORS:
                    name = sep.join(combo)
                    bases[name] = max(bases.get(name, 0), 65 * SEP_WEIGHT[sep])

        # 3) primario + primario + complementar (uniao + regiao)
        if len(t_reps) > 1 and m_reps:
            for combo in permutations(t_reps, 2):
                for mr in m_reps:
                    for sep in ("-", "."):
                        name = f"{sep.join(combo)}{sep}{mr}"
                        bases[name] = max(bases.get(name, 0), 45 * SEP_WEIGHT[sep])

    return bases


def add(results, name, score):
    if name:
        results[name] = max(results.get(name, 0.0), score)


def apply_affixes(base, base_score, results, opts):
    # base sozinha
    add(results, base, base_score)

    func_pool = dict(FUNCS)
    if opts["ptbr"]:
        func_pool.update(FUNCS_PTBR)

    # ---- afixo unico ----
    for aff, w in ENVS.items():
        for sep in SEPARATORS:
            sw = SEP_WEIGHT[sep]
            add(results, f"{aff}{sep}{base}", base_score * 0.5 + w * POS_ENV_PREFIX * sw)
            add(results, f"{base}{sep}{aff}", base_score * 0.5 + w * POS_ENV_SUFFIX * sw)
    for aff, w in func_pool.items():
        for sep in SEPARATORS:
            sw = SEP_WEIGHT[sep]
            add(results, f"{aff}{sep}{base}", base_score * 0.5 + w * POS_FUNC_PREFIX * sw)
            add(results, f"{base}{sep}{aff}", base_score * 0.5 + w * POS_FUNC_SUFFIX * sw)

    # ---- afixos compostos: base + func + env ----
    if opts["composite"]:
        top_funcs = sorted(func_pool.items(), key=lambda x: -x[1])[:8]
        top_envs = sorted(ENVS.items(), key=lambda x: -x[1])[:5]
        for fn, fw in top_funcs:
            for ev, ew in top_envs:
                for sep in ("-", ".", "_"):
                    sw = SEP_WEIGHT[sep]
                    cs = base_score * 0.35 + (fw + ew) * 0.4 * sw
                    add(results, f"{base}{sep}{fn}{sep}{ev}", cs)        # example-api-prd
                    add(results, f"{ev}{sep}{base}{sep}{fn}", cs * 0.9)  # prd-example-api
                    add(results, f"{base}{sep}{ev}{sep}{fn}", cs * 0.85)
            # func + func (static-assets)
        composite_funcs = [("static", "assets"), ("media", "uploads"),
                           ("api", "data"), ("app", "logs"), ("web", "assets")]
        for a, b in composite_funcs:
            for sep in ("-", "."):
                add(results, f"{base}{sep}{a}{sep}{b}", base_score * 0.3 + 55 * SEP_WEIGHT[sep])

    # ---- regioes ----
    if opts["regions"]:
        for rg, w in REGIONS.items():
            for sep in ("-", "."):
                add(results, f"{base}{sep}{rg}", base_score * 0.4 + w * SEP_WEIGHT[sep])

    # ---- anos ----
    if opts["years"]:
        for yr, w in YEARS.items():
            for sep in ("-", "_", "."):
                add(results, f"{base}{sep}{yr}", base_score * 0.4 + w * SEP_WEIGHT[sep])
                add(results, f"{base}-backup{sep}{yr}", base_score * 0.3 + w * 0.8)

    # ---- account id placeholder ----
    if opts["account"]:
        for sep in ("-", "."):
            add(results, f"{base}{sep}ACCOUNTID", base_score * 0.3 + 40 * SEP_WEIGHT[sep])
            add(results, f"ACCOUNTID{sep}{base}", base_score * 0.3 + 38 * SEP_WEIGHT[sep])

    # ---- wordlist externa ----
    for aff in opts["extra"]:
        for sep in ("-", ".", "_"):
            add(results, f"{aff}{sep}{base}", base_score * 0.4 + 50 * SEP_WEIGHT[sep])
            add(results, f"{base}{sep}{aff}", base_score * 0.4 + 50 * SEP_WEIGHT[sep])


def is_valid_bucket(name: str) -> bool:
    if not (3 <= len(name) <= 63):
        return False
    if name[0] in "-._" or name[-1] in "-._":
        return False
    if ".." in name or ".-" in name or "-." in name:
        return False
    return True


def _yn(prompt, default=True):
    d = "S/n" if default else "s/N"
    try:
        ans = input(f"{prompt} [{d}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[!] cancelado.", file=sys.stderr)
        sys.exit(1)
    if not ans:
        return default
    return ans in ("s", "sim", "y", "yes")


def interactive_prompt(args):
    """Pergunta o essencial quando o script roda sem termos."""
    import shlex

    def _split(raw):
        try:
            return shlex.split(raw)
        except ValueError:
            return raw.split()

    print("=== bucketgen :: modo interativo ===", file=sys.stderr)
    print("(deixe vazio p/ aceitar o padrao entre colchetes)\n", file=sys.stderr)

    # --- primarios (alvo) ---
    while not args.targets:
        try:
            raw = input("Termos PRINCIPAIS / alvo? (ex: example google)\n"
                        "(separe por espaco; use aspas p/ multi-palavra)\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[!] cancelado.", file=sys.stderr)
            sys.exit(1)
        if not raw:
            print("[!] precisa de pelo menos um termo principal.", file=sys.stderr)
            continue
        args.targets = _split(raw)

    # --- complementares (modificadores) ---
    try:
        raw = input("Termos COMPLEMENTARES? (ex: web cloud \"data lake\")\n"
                    "(so anexam a um principal, nunca isolados; vazio = nenhum)\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    args.mod = _split(raw) if raw else []

    has_combos = len(args.targets) > 1 or bool(args.mod)
    if has_combos:
        args.combine = _yn("Combinar termos? (example-web, example-google)", True)
    args.composite = _yn("Incluir afixos compostos? (api-prd, static-assets)", True)
    args.ptbr = _yn("Incluir funcoes em PT-BR? (boletos, arquivos, documentos)", True)
    args.years = _yn("Incluir anos? (2020-2025)", True)
    args.regions = _yn("Incluir regioes AWS? (sa-east-1...)", False)
    args.account = _yn("Incluir placeholder de account-id?", False)

    if not args.output:
        try:
            out = input("Arquivo de saida? (vazio = imprime na tela)\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            out = ""
        if out:
            args.output = out
    print("", file=sys.stderr)
    return args


def main():
    p = argparse.ArgumentParser(description="Gera wordlist ranqueada p/ enum de buckets.")
    p.add_argument("terms", nargs="*",
                   help="Termo(s) primario(s) posicionais (alias de --target). Vazio = modo interativo.")
    p.add_argument("-t", "--target", nargs="+", default=[],
                   help="Termo(s) PRIMARIO(s)/alvo. Cada um gera wordlist completa.")
    p.add_argument("-m", "--mod", nargs="+", default=[],
                   help="Termo(s) COMPLEMENTAR(es). So anexam a um primario (example-web), nunca isolados.")
    p.add_argument("-o", "--output", help="Arquivo de saida (default: stdout).")
    p.add_argument("--max", type=int, default=0, help="Limite de linhas (0=ilimitado).")
    p.add_argument("--valid-only", action="store_true", help="So nomes validos S3.")
    p.add_argument("--wordlist", help="Arquivo com afixos extras (1 por linha).")
    p.add_argument("--scores", action="store_true", help="Mostra score ao lado (debug).")
    # toggles (todos ligados por default)
    p.add_argument("--no-combine", dest="combine", action="store_false")
    p.add_argument("--no-composite", dest="composite", action="store_false")
    p.add_argument("--no-regions", dest="regions", action="store_false")
    p.add_argument("--no-years", dest="years", action="store_false")
    p.add_argument("--no-account", dest="account", action="store_false")
    p.add_argument("--no-ptbr", dest="ptbr", action="store_false")
    p.set_defaults(combine=True, composite=True, regions=True,
                   years=True, account=True, ptbr=True)
    args = p.parse_args()

    # primarios = posicionais + --target (posicional eh alias de target)
    args.targets = list(args.terms) + list(args.target)

    # ---- modo interativo: rodou sem nenhum primario ----
    if not args.targets:
        args = interactive_prompt(args)

    extra = []
    if args.wordlist:
        try:
            with open(args.wordlist) as f:
                extra = [normalize(l) for l in f if l.strip() and not l.startswith("#")]
        except OSError as e:
            print(f"[!] wordlist: {e}", file=sys.stderr)
            sys.exit(1)

    opts = {"composite": args.composite, "regions": args.regions,
            "years": args.years, "account": args.account,
            "ptbr": args.ptbr, "extra": extra}

    bases = build_bases(args.targets, args.mod, args.combine)
    results = {}
    for b, bs in bases.items():
        apply_affixes(b, bs, results, opts)

    items = [(n, s) for n, s in results.items() if n]
    if args.valid_only:
        items = [(n, s) for n, s in items if is_valid_bucket(n)]
    # ranqueia: score desc, depois nome (estabilidade)
    items.sort(key=lambda x: (-x[1], x[0]))
    if args.max > 0:
        items = items[:args.max]

    if args.scores:
        lines = [f"{s:6.1f}  {n}" for n, s in items]
    else:
        lines = [n for n, _ in items]
    text = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"[+] {len(items)} entradas ranqueadas -> {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
