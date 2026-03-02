# API eSoccer — Guia para o Frontend

## Acesso

| | |
|---|---|
| **Base URL** | `https://api-esoccer.arvsystems.cloud` |
| **Swagger UI** | `https://api-esoccer.arvsystems.cloud/docs` |
| **Autenticação** | Header `X-API-Key: <sua_chave>` |

> No Swagger: clique em **Authorize** (canto superior direito), cole a API Key e teste direto no browser.

---

## Autenticação

Todos os endpoints (exceto `GET /strategies` e `GET /health`) exigem o header:

```
X-API-Key: <sua_chave>
```

Sem ele ou com chave errada → `401 Unauthorized`.

---

## Endpoints

### `GET /strategies`

Lista as estratégias disponíveis. **Não requer autenticação.**

**Request:**
```http
GET /strategies
```

**Response `200`:**
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

Use o campo `id` exatamente como está para chamar o `/analyze`.

---

### `POST /analyze`

Processa os arquivos `.xlsx` e retorna as métricas. Usa cache Redis — segunda chamada com os mesmos arquivos retorna imediatamente.

**Request:**
```http
POST /analyze
X-API-Key: <sua_chave>
Content-Type: multipart/form-data

files: [arquivo1.xlsx, arquivo2.xlsx, ...]
strategy: "eSoccer — Dupla"
```

**Response `200` — eSoccer (sem campo `linha`):**
```json
{
  "cache_hit": false,
  "cache_key": "a3f8c2d1e9b4f7a2c5d8e1f3b6a9c2d5",
  "strategy": "eSoccer — Dupla",
  "total_jogos_brutos": 16163,
  "total_jogos_apos_dedup": 12847,
  "duplas": [
    {
      "dupla": "Agent vs Force",
      "ligas": "Liga A / Liga B",
      "fontes": ["365", "Betano"],
      "quantidade_entradas": 24,
      "quantidade_greens": 14,
      "percentual_green": 58.3,
      "pontuacao": -16,
      "ultimos_6": "G-R-G-G-R-G",
      "pct_green_10": 60.0,
      "quantidade_reds": 10,
      "max_reds": 3,
      "reds_apos_red": 4,
      "sistema_red_pct": 40.0,
      "srpt": 1.23,
      "sequencia_atual_g": 2,
      "max_greens": 5,
      "lucro_prej_total": 2.03
    }
  ]
}
```

**Response `200` — Over/HT (inclui campo `linha`):**
```json
{
  "cache_hit": false,
  "cache_key": "b7d2e4f1a8c3d6e9f2a5b8c1d4e7f0a3",
  "strategy": "Over/HT — Dupla + Linha",
  "total_jogos_brutos": 8420,
  "total_jogos_apos_dedup": 7105,
  "duplas": [
    {
      "dupla": "Agent vs Force",
      "linha": "Over 0.5 HT",
      "ligas": "Liga A",
      "fontes": ["Super"],
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

**Campos da resposta:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `cache_hit` | bool | `true` se retornou do cache |
| `cache_key` | string | Chave MD5 (use para `/export`) |
| `strategy` | string | Nome da estratégia usada |
| `total_jogos_brutos` | int | Total de linhas lidas dos arquivos |
| `total_jogos_apos_dedup` | int | Total após deduplicação |
| `duplas` | array | Resultados por dupla (filtrados) |
| `dupla` | string | Confronto normalizado |
| `linha` | string | Linha de mercado **(só Over/HT)** |
| `ligas` | string | Torneios separados por ` / ` |
| `fontes` | `list[string]` | Casas de apostas onde a dupla aparece. Ex: `["365", "Betano"]` |
| `quantidade_entradas` | int | Total de jogos |
| `quantidade_greens` | int | Total de greens |
| `percentual_green` | float | % de greens |
| `pontuacao` | int | Score (+1 green / -3 red) |
| `ultimos_6` | string | Ex: `"G-R-G-G-R-G"` |
| `pct_green_10` | float | % green nos últimos 10 jogos |
| `quantidade_reds` | int | Total de reds |
| `max_reds` | int | Maior sequência de reds |
| `reds_apos_red` | int | Reds consecutivos (Sistema Red) |
| `sistema_red_pct` | float | % do Sistema Red |
| `srpt` | float | Score ponderado por recência |
| `sequencia_atual_g` | int | Greens consecutivos atuais |
| `max_greens` | int | Maior sequência de greens |
| `lucro_prej_total` | float | Lucro/Prejuízo acumulado |

**Errors:**
- `401` — API Key ausente ou inválida
- `422` — `strategy` não encontrada (use `GET /strategies` para listar)

---

### `GET /export/{cache_key}`

Baixa o resultado de uma análise já processada como `.xlsx`.
O `cache_key` vem do response do `/analyze`.

**Request:**
```http
GET /export/a3f8c2d1e9b4f7a2c5d8e1f3b6a9c2d5
X-API-Key: <sua_chave>
```

**Response `200`:** arquivo `.xlsx` (download direto)

**Errors:**
- `404` — cache expirou (TTL 1h) ou `cache_key` inválida — rode `/analyze` novamente

---

### `GET /cache/status`

Estatísticas do Redis.

**Response `200`:**
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

### `GET /health`

Health check. **Não requer autenticação.**

**Response `200`:** `{ "status": "ok" }`

---

### `POST /analyze/default`

Analisa usando os arquivos pré-carregados no servidor. **Não requer upload de arquivo.**
Ideal para desenvolvimento frontend — não precisa gerenciar arquivos `.xlsx`.

**Request:**
```http
POST /analyze/default
X-API-Key: <sua_chave>
Content-Type: application/json

{"strategy": "eSoccer — Dupla"}
```

**Response `200`:** idêntico ao `POST /analyze`. O `cache_key` retornado também funciona com `GET /export/{cache_key}`.

**Errors:**
- `422` — `strategy` não encontrada
- `503` — arquivos não configurados no servidor (contactar o administrador)

> **Cache compartilhado:** se os mesmos arquivos já foram analisados via `POST /analyze`,
> a resposta será imediata (`cache_hit: true`).

---

## Exemplos de Integração

### JavaScript (fetch)

```js
const BASE_URL = "https://api-esoccer.arvsystems.cloud";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

// Listar estratégias
async function getStrategies() {
  const res = await fetch(`${BASE_URL}/strategies`);
  return res.json();
}

// Analisar arquivos
async function analyze(files, strategy) {
  const form = new FormData();
  form.append("strategy", strategy);
  for (const file of files) {
    form.append("files", file);
  }

  const res = await fetch(`${BASE_URL}/analyze`, {
    method: "POST",
    headers: { "X-API-Key": API_KEY },
    body: form,
  });

  if (!res.ok) throw new Error(`Erro ${res.status}: ${await res.text()}`);
  return res.json();
}

// Baixar xlsx
async function exportXlsx(cacheKey) {
  const res = await fetch(`${BASE_URL}/export/${cacheKey}`, {
    headers: { "X-API-Key": API_KEY },
  });
  if (!res.ok) throw new Error("Export não encontrado");
  return res.blob(); // use URL.createObjectURL(blob) para download
}
```

### curl

```bash
# Listar estratégias
curl https://api-esoccer.arvsystems.cloud/strategies

# Analisar (eSoccer)
curl -X POST https://api-esoccer.arvsystems.cloud/analyze \
  -H "X-API-Key: SUA_CHAVE" \
  -F "strategy=eSoccer — Dupla" \
  -F "files=@BETANO.xlsx"

# Analisar (Over/HT com 2 arquivos)
curl -X POST https://api-esoccer.arvsystems.cloud/analyze \
  -H "X-API-Key: SUA_CHAVE" \
  -F "strategy=Over/HT — Dupla + Linha" \
  -F "files=@BETANO.xlsx" \
  -F "files=@365.xlsx"

# Exportar xlsx
curl https://api-esoccer.arvsystems.cloud/export/<cache_key> \
  -H "X-API-Key: SUA_CHAVE" \
  -o analise.xlsx
```

---

## Comportamento do Cache

- **Mesmos arquivos + mesma estratégia** → `cache_hit: true`, resposta imediata
- **Cache de análise:** 24h
- **Cache de export (.xlsx):** 1h — se expirou, rode `/analyze` novamente (o resultado já estará em cache, só o xlsx é regenerado)
- A ordem dos arquivos no upload **não afeta** o cache_key

---

## Variáveis de Ambiente (Next.js)

```env
# .env.local
NEXT_PUBLIC_API_URL=https://api-esoccer.arvsystems.cloud
NEXT_PUBLIC_API_KEY=<sua_chave>
```

> A API Key não deve ser exposta em código client-side em produção.
> Use uma rota de API do Next.js (`/api/analyze`) como proxy para esconder a chave.
