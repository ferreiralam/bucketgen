# bucketgen

Gerador inteligente de wordlists para enumeração de buckets em nuvem (S3 / GCS / Azure Blob).

O `bucketgen` recebe um ou mais nomes-alvo e gera uma wordlist **ranqueada por
probabilidade** de nomes prováveis de bucket. Os candidatos mais prováveis vêm
primeiro — então quando você joga a lista num resolver com *rate limit*, os
*hits* reais aparecem nas primeiras centenas de linhas em vez de ficarem
enterrados no meio do ruído.

> 🇬🇧 English version: [README.en.md](README.en.md)

## Por quê

Ferramentas genéricas de permutação tratam todos os termos como iguais e
combinam tudo com tudo, gerando listas enormes e de baixa qualidade. O
`bucketgen` separa os termos **principais** (o alvo real) dos termos
**complementares** (modificadores como região ou nome de produto), pontua cada
candidato segundo padrões vistos em buckets reais, e ordena a saída por isso.

## Recursos

- **Ranking por probabilidade** — candidatos pontuados pela frequência do padrão
  em buckets reais (`prd-`, `-backup`, `-assets` pontuam alto; `tst-`, `demo-` baixo).
- **Termos principais x complementares** — principais geram wordlist completa;
  modificadores só se anexam a um principal (`example-web`), nunca isolados.
- **Afixos compostos** — `example-api-prd`, `example-static-assets`, `prd-example-backup`.
- **Regiões AWS** — `sa-east-1` priorizado, mais as regiões US/EU comuns.
- **Anos** — `example-2024`, `example-backup-2023`.
- **Placeholder de account-id** — emite `example-ACCOUNTID` para substituição posterior.
- **Funções em PT-BR** — `boletos`, `arquivos`, `documentos`, `notasfiscais`...
  (útil para alvos de escopo brasileiro que wordlists em inglês não cobrem).
- **Wordlist externa** — injete seus próprios termos de recon via `--wordlist`.
- **Modo interativo** — rode sem argumentos e ele pergunta o essencial.
- **Validação de nome S3** — `--valid-only` mantém só nomes válidos de bucket.

## Requisitos

Python 3.6+ (apenas biblioteca padrão, sem dependências externas).

## Uso

```bash
# um único alvo principal
python3 bucketgen.py example

# principais (-t) + modificadores complementares (-m)
python3 bucketgen.py -t example google -m web cloud "data lake"

# limita a saída e mantém só nomes S3 válidos
python3 bucketgen.py -t example -m web --max 5000 --valid-only

# mostra os scores (debug / calibração)
python3 bucketgen.py example --scores | head -30

# salva em arquivo
python3 bucketgen.py -t example google -m web -o buckets.txt

# usa seus próprios termos de recon
python3 bucketgen.py example --wordlist recon_extra.txt

# modo interativo (pergunta termos principais + complementares)
python3 bucketgen.py
```

### Principais x complementares

| Tipo de termo | Flag | Comportamento | Saída de exemplo |
|---------------|------|---------------|------------------|
| Principal | posicional ou `-t/--target` | wordlist completa sozinho | `prd-example`, `example-backup` |
| Complementar | `-m/--mod` | só se anexa a um principal | `example-web`, `prd-example-web` |

Um termo complementar **nunca** é emitido sozinho — nada de `prd-web` ou
`web-backup`. Ele só existe colado a um principal.

### Flags

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `-t`, `--target` | — | Termo(s) principal(is)/alvo. |
| `-m`, `--mod` | — | Termo(s) complementar(es); só anexam a um principal. |
| `-o`, `--output` | stdout | Arquivo de saída. |
| `--max N` | 0 (ilimitado) | Mantém só as N melhores entradas ranqueadas. |
| `--valid-only` | off | Mantém só nomes de bucket S3 válidos. |
| `--wordlist ARQUIVO` | — | Afixos extras, um por linha (`#` para comentários). |
| `--scores` | off | Imprime o score ao lado de cada entrada. |
| `--no-combine` | on | Desativa combinação de termos. |
| `--no-composite` | on | Desativa afixos compostos. |
| `--no-regions` | on | Desativa mutações de região AWS. |
| `--no-years` | on | Desativa mutações de ano. |
| `--no-account` | on | Desativa o placeholder de account-id. |
| `--no-ptbr` | on | Desativa as funções em português. |

### Placeholder de account-id

Quando `--no-account` **não** está setado, a ferramenta emite candidatos com a
string literal `ACCOUNTID`:

```
example-ACCOUNTID
ACCOUNTID-example
```

Quando você descobrir o account-id real (12 dígitos) da AWS, substitua em toda
a lista:

```bash
sed 's/ACCOUNTID/123456789012/g' buckets.txt > buckets-final.txt
```

## Integração com Nuclei

A wordlist gerada se encaixa direto nos *templates* de enumeração de bucket do
[nuclei-templates](https://github.com/projectdiscovery/nuclei-templates), que
recebem a lista pela variável `wordlist`.

```bash
# 1) gere a wordlist (top 10k válidos é um bom ponto de partida)
python3 bucketgen.py -t example google -m web --valid-only --max 10000 -o buckets.txt

# 2) AWS S3
nuclei -t ~/nuclei-templates/cloud/enum/aws-s3-bucket-enum.yaml \
  -var wordlist=buckets.txt -esc -lfa

# 3) GCP Storage
nuclei -t ~/nuclei-templates/cloud/enum/gcp-bucket-enum.yaml \
  -var wordlist=buckets.txt -esc -lfa
```

**O que cada flag faz:**

- `-t` — caminho do *template* de enumeração (S3 ou GCP).
- `-var wordlist=buckets.txt` — passa a wordlist do `bucketgen` para a variável
  `wordlist` que o *template* consome. Use o mesmo arquivo nos dois.
- `-esc` (`-enable-self-contained`) — habilita *templates* self-contained; os
  *templates* de enum de cloud são *code/self-contained* e não rodam sem isso.
- `-lfa` (`-allow-local-file-access`) — permite o acesso a arquivo local
  necessário para o *template* ler a wordlist do disco.

> **Atenção:** confira o caminho dos *templates*. Em versões recentes do
> nuclei-templates os arquivos de enum de cloud podem estar em
> `cloud/enum/` ou em outro subdiretório — ajuste o `-t` conforme a sua árvore:
> `find ~/nuclei-templates -name '*bucket-enum*'`

### Dica de fluxo

```bash
# gera, ranqueia, corta no topo e já enumera S3 + GCP na sequência
python3 bucketgen.py -t example -m web cloud --valid-only --max 8000 -o buckets.txt
for tpl in aws-s3-bucket-enum gcp-bucket-enum; do
  nuclei -t ~/nuclei-templates/cloud/enum/$tpl.yaml -var wordlist=buckets.txt -esc -lfa
done
```

Como a saída do `bucketgen` já vem ranqueada, mesmo cortando com `--max` você
mantém os candidatos de maior probabilidade — bom para economizar requisições
quando o alvo tem *rate limit* ou quando a chamada de API tem custo.

## Aviso legal

Esta ferramenta destina-se **somente a testes de segurança autorizados**. Use
apenas contra ativos que você possui ou tem permissão explícita para testar
(escopo de *bug bounty*, contrato assinado, sua própria infraestrutura). O autor
não se responsabiliza por uso indevido. Sempre confirme o escopo antes de
enumerar.

## Licença

MIT — veja [LICENSE](LICENSE).
