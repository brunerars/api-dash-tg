# CLAUDE.md v3 — Backend FastAPI + Redis — dash-tg

## Visão Geral

API backend para o dashboard de análise eSoccer multi-estratégia.
Consome planilhas `.xlsx`, processa métricas e serve resultados via HTTP com cache Redis.
O frontend (qualquer tecnologia) consome a API hospedada na VPS sem dependência da engine.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI + Python 3.11 |
| Processamento | pandas + openpyxl |
| Cache | Redis 7 + redis-py |
| Autenticação | API Key via header `X-API-Key` |
| Deploy | Docker Compose na VPS |
| Documentação | Swagger automático (`/docs`) |

---

## Estrutura de Pastas

```
dash-tg/
├── main.py
├── routers/
│   └── analysis.py
├── esoccer_dashboard/services/
│   ├── loader.py          # leitura dos .xlsx
│   ├── normalizer.py      # normalização de duplas
│   ├── deduplicator.py    # cluster ≤ 5 min — recebe dedup_key da estratégia
│   ├── metrics.py         # cálculo das 16 métricas — recebe config da estratégia
│   └── cache.py           # integração Redis
├── config/
│   ├── strategies.py      # fonte da verdade — parâmetros completos por estratégia
│   └── settings.py        # variáveis de ambiente
├── middleware/
│   └── auth.py            # validação API Key
├── tests/
│   └── test_deduplicator.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Configuração de Estratégias (`config/strategies.py`)

**Fonte da verdade única.** Cada estratégia define seu comportamento completo.
`metrics.py` e `deduplicator.py` recebem esses parâmetros — nunca têm valores hardcoded.

```python
ESTRATEGIAS = {
    "eSoccer — Dupla": {
        "group_by": ["Dupla"],
        "dedup_key": ["Dupla", "Data"],
        "min_jogos": 6,
        "min_green_pct": 35,
        "sistema_red_janela_horas": None,
        "descricao": "Analisa por confronto entre jogadores",
    },
    "Over/HT — Dupla + Linha": {
        "group_by": ["Dupla", "Linha"],
        "dedup_key": ["Dupla", "Linha", "Data"],
        "min_jogos": 4,
        "min_green_pct": 65,
        "sistema_red_janela_horas": 12,
        "descricao": "Over e HT — analisa por confronto e linha de mercado",
    },
}
# Para adicionar nova estratégia: apenas adicionar entrada aqui.
# NUNCA alterar metrics.py ou deduplicator.py para isso.
```

### Parâmetros documentados

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `group_by` | `list[str]` | Colunas de agrupamento para cálculo das métricas |
| `dedup_key` | `list[str]` | Colunas usadas para identificar clusters de deduplicação |
| `min_jogos` | `int` | Mínimo de jogos para exibição após dedup |
| `min_green_pct` | `float` | Mínimo de % GREEN para exibição |
| `sistema_red_janela_horas` | `int\|None` | `None` = só mesmo dia / `12` = mesmo dia OU até 12h entre jogos |

> "Dupla" em `group_by`/`dedup_key` é shorthand de documentação.
> `get_strategy_internal()` traduz para o nome real de coluna `DuplaNormalizada`.

### Diferenças entre estratégias

| Regra | eSoccer | Over/HT |
|-------|---------|---------|
| Agrupamento | Dupla | Dupla + Linha |
| Cluster dedup | Dupla + Data | Dupla + Linha + Data |
| Mínimo de jogos | 6 | 4 |
| Mínimo % GREEN | 35% | 65% |
| Sistema Red janela | mesmo dia | mesmo dia OU até 12h |

---

## Endpoints

### `POST /analyze`

Recebe os arquivos e a estratégia, verifica cache, processa se necessário.

**Headers:**
```
X-API-Key: {chave_do_cliente}
Content-Type: multipart/form-data
```

**Body:**
```
files: [arquivo1.xlsx, arquivo2.xlsx, ...]
strategy: "eSoccer — Dupla"
```

**Lógica interna:**
```python
# 1. Validar API Key
# 2. Carregar config de ESTRATEGIAS[strategy] via get_strategy_internal()
# 3. Gerar cache_key = MD5(bytes de todos os arquivos + strategy)
# 4. Verificar Redis
#    HIT  → retornar dados do cache imediatamente
#    MISS → pipeline completo → salvar no Redis (TTL 24h) → retornar
```

**Response 200:**
```json
{
  "cache_hit": false,
  "cache_key": "a3f8c2...",
  "strategy": "Over/HT — Dupla + Linha",
  "total_jogos_brutos": 16163,
  "total_jogos_apos_dedup": 12847,
  "duplas": [
    {
      "dupla": "Agent vs Force",
      "linha": "Over 0.5 HT",
      "ligas": "Liga A / Liga B",
      "quantidade_entradas": 12,
      "quantidade_greens": 9,
      "percentual_green": 75.0,
      "pontuacao": 0,
      "ultimos_6": "G-G-R-G-G-G",
      "pct_green_10": 70.0,
      "quantidade_reds": 3,
      "max_reds": 1,
      "reds_apos_red": 1,
      "sistema_red_pct": 33.3,
      "srpt": 2.14,
      "sequencia_atual_g": 3,
      "max_greens": 4,
      "lucro_prej_total": 5.20
    }
  ]
}
```

> O campo `"linha"` só aparece quando `group_by` da estratégia inclui `"Linha"`.

---

### `GET /strategies`

Lista as estratégias disponíveis com seus parâmetros principais.

**Response 200:**
```json
{
  "strategies": [
    {
      "id": "eSoccer — Dupla",
      "descricao": "Analisa por confronto entre jogadores",
      "min_jogos": 6,
      "min_green_pct": 35
    },
    {
      "id": "Over/HT — Dupla + Linha",
      "descricao": "Over e HT — analisa por confronto e linha de mercado",
      "min_jogos": 4,
      "min_green_pct": 65
    }
  ]
}
```

---

### `GET /export/{cache_key}`

Retorna o resultado de uma análise já processada como arquivo `.xlsx` para download.
O `cache_key` é retornado no response do `/analyze`.

**Headers:**
```
X-API-Key: {chave_do_cliente}
```

**Response:** arquivo `.xlsx` como download direto.

---

### `GET /cache/status` *(admin)*

Retorna saúde e estatísticas do Redis.

**Response 200:**
```json
{
  "status": "ok",
  "total_chaves": 42,
  "memoria_usada": "3.21 MB",
  "hits": 318,
  "misses": 44,
  "hit_rate": "87.8%",
  "uptime_horas": 72
}
```

---

### `DELETE /cache/{cache_key}` *(admin)*

Invalida manualmente uma entrada do cache.

---

## Regras de Negócio (NÃO ALTERAR)

### Pipeline obrigatório (ordem inviolável)

```
1. Ler todos os arquivos → apenas aba "Tips Enviadas"
2. Validar colunas obrigatórias
3. Criar coluna DataHora (Data + Hora) — formato BR com segundos
4. Criar coluna Dupla normalizada
5. Executar deduplicação por cluster ≤ 5 minutos (usando dedup_key da estratégia)
6. CONGELAR o dataset — nenhuma linha pode ser adicionada depois
7. Calcular métricas com group_by da estratégia selecionada
8. Aplicar filtros de exibição (min_jogos e min_green_pct da estratégia)
```

### Deduplicação (`deduplicator.py`)

Recebe `dedup_key` como parâmetro da estratégia.

```python
def deduplicate_clusters(df, dedup_key: list[str], window_minutes=5) -> DedupResult:
    # Cluster por: dedup_key + diferença de horário ≤ janela_minutos
    # entre linhas de arquivos diferentes
    # Manter apenas a linha com horário mais tardio
```

Regras invariáveis:
- Diferença absoluta de horário ≤ 5 minutos
- Manter linha com horário mais tardio
- Roda antes de qualquer cálculo — sem exceções
- Proibido deduplicar apenas por DataHora exata

### Normalização de duplas (`normalizer.py`)

- Ordenar nomes alfabeticamente
- Preservar sufixos `(2x6)`, `(ECF Volta)`, `(ECF)` sem duplicar
- `"Cevuu vs Elmagico (2x6) (2x6)"` → `"Cevuu (2x6) vs Elmagico (2x6)"`

### Sistema Red

```python
def _reds_after_red(resultados, datas, datahoras, janela_horas):
    # Se janela_horas is None:
    #   contar RED seguido de RED apenas no mesmo dia (Data idêntica)
    # Se janela_horas = 12:
    #   contar RED seguido de RED se mesmo dia
    #   OU se dias diferentes mas diferença entre DataHora ≤ 12h
```

### SRPT

```python
peso = 0.5 ** (distancia / 10)   # meia-vida 10 jogos
valor = +1 if green else -3
SRPT = sum(peso * valor)
```

### Filtros de exibição

Valores lidos da estratégia — nunca hardcoded no router.

```python
df = df[df["quantidade_entradas"] >= estrategia["min_jogos"]]
df = df[df["percentual_green"] >= estrategia["min_green_pct"]]
```

---

## Colunas de Saída

16 colunas padrão + coluna `linha` quando `group_by` inclui `"Linha"`.

| Coluna | eSoccer | Over/HT |
|--------|---------|---------|
| ligas | ✓ | ✓ |
| dupla | ✓ | ✓ |
| linha | — | ✓ |
| quantidade_entradas | ✓ | ✓ |
| quantidade_greens | ✓ | ✓ |
| percentual_green | ✓ | ✓ |
| pontuacao | ✓ | ✓ |
| ultimos_6 | ✓ | ✓ |
| pct_green_10 | ✓ | ✓ |
| quantidade_reds | ✓ | ✓ |
| max_reds | ✓ | ✓ |
| reds_apos_red | ✓ | ✓ |
| sistema_red_pct | ✓ | ✓ |
| srpt | ✓ | ✓ |
| sequencia_atual_g | ✓ | ✓ |
| max_greens | ✓ | ✓ |
| lucro_prej_total | ✓ | ✓ |

---

## Cache (`services/cache.py`)

### Geração da chave
```python
def gerar_cache_key(files_bytes: list[bytes], strategy: str) -> str:
    h = hashlib.md5()
    for b in sorted(files_bytes):  # sorted para ordem não importar
        h.update(b)
    h.update(strategy.encode())
    return h.hexdigest()
```

### TTL por tipo de dado
| Dado | TTL |
|------|-----|
| Resultado de análise | 24h |
| Export `.xlsx` | 1h |
| Lista de estratégias | sem expiração (estático) |

---

## Autenticação (`middleware/auth.py`)

```python
API_KEYS = set(os.getenv("API_KEYS", "").split(","))

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="API Key inválida")
```

---

## Docker Compose

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

---

## Variáveis de Ambiente (`.env`)

```env
API_KEYS=chave_cliente1,chave_cliente2
REDIS_URL=redis://redis:6379
CACHE_TTL_ANALYSIS=86400
CACHE_TTL_EXPORT=3600
```

---

## O que NÃO muda entre estratégias

- Lógica de deduplicação (só o `dedup_key` muda)
- Normalização de nomes de duplas
- Fórmula SRPT (meia-vida 10 jogos)
- Estrutura dos endpoints e formato do response
- Para adicionar estratégia: apenas editar `config/strategies.py`
