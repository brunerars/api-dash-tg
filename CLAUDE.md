# CLAUDE.md — Dashboard de Análise eSoccer

## Visão Geral do Projeto

Dashboard web para análise estatística de duplas de eSoccer (FIFA) a partir de planilhas exportadas de bots de apostas.
O usuário faz upload de uma ou mais planilhas `.xlsx`, o sistema processa, deduplica, calcula métricas e exibe um dashboard interativo.

---

## Stack Tecnológica

| Camada     | Tecnologia              |
|------------|------------------------|
| Backend    | FastAPI + Python 3.11  |
| Processamento | pandas + openpyxl   |
| Frontend   | Next.js 14 (App Router) + TailwindCSS |
| Tabelas    | TanStack Table v8      |
| Deploy     | Docker Compose         |

> Alternativa rápida: substituir Next.js por Streamlit para entrega em 2-3 dias.

---

## Estrutura de Pastas

```
esoccer-dashboard/
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── routers/
│   │   └── analysis.py          # POST /analyze
│   ├── services/
│   │   ├── loader.py            # Leitura das planilhas
│   │   ├── deduplicator.py      # Etapa de deduplicação (ISOLADA)
│   │   ├── normalizer.py        # Normalização de nomes de duplas
│   │   └── metrics.py           # Cálculo de todas as métricas
│   ├── models/
│   │   └── schemas.py           # Pydantic schemas
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Upload + Dashboard
│   │   └── components/
│   │       ├── UploadZone.tsx
│   │       ├── AnalysisTable.tsx
│   │       └── FiltersBar.tsx
│   └── package.json
├── docker-compose.yml
└── CLAUDE.md
```

---

## Regras de Negócio Críticas (NÃO ALTERAR)

### 1. Fonte de Dados
- Ler **apenas** a aba `Tips Enviadas` de cada arquivo `.xlsx`
- Colunas obrigatórias: `Torneio`, `Confronto`, `Data`, `Hora`, `Resultado`, `Lucro/Prej.`

### 2. Normalização de Duplas
- Ordenar nomes alfabeticamente: `"Force vs Agent"` → `"Agent vs Force"`
- Preservar sufixos: `(2x6)`, `(ECF Volta)`, `(ECF)`
- Tratar como mesma dupla: `"Cevuu vs Elmagico (2x6) (2x6)"` = `"Cevuu (2x6) vs Elmagico (2x6)"`
- Lógica: extrair sufixos por jogador, reordenar e recompor

### 3. Deduplicação (ETAPA OBRIGATÓRIA ANTES DE QUALQUER CÁLCULO)

```
ORDEM DE EXECUÇÃO — NÃO QUEBRAR ESTA SEQUÊNCIA:
1. Ler todos os arquivos
2. Filtrar apenas aba "Tips Enviadas"
3. Criar coluna DataHora (Data + Hora)
4. Criar coluna Dupla normalizada
5. Executar deduplicação completa por cluster ≤ 5 minutos
6. Congelar o dataset (nenhuma linha pode ser adicionada depois)
7. Iniciar os cálculos de métricas
```

**Regra do cluster:**
- Mesma Dupla normalizada
- Mesmo dia (Data idêntica)
- Diferença de horário ≤ 5 minutos entre linhas de arquivos diferentes
- Manter apenas a linha com horário **mais tardio**

**Proibições absolutas:**
- ❌ Somar jogos antes da deduplicação completa
- ❌ Aplicar filtros mínimos antes da deduplicação
- ❌ Contar bots diferentes como jogos distintos no mesmo cluster
- ❌ Deduplicar apenas por DataHora exata (deve usar janela de 5 min)

### 4. Filtros para exibição
- Mínimo de **6 partidas** por dupla
- Mínimo de **35% de acerto (GREEN)**

### 5. Mapeamento de Resultados
- `"Green"` → GREEN → `+1` ponto
- `"Red"` → RED → `-3` pontos

---

## Métricas a Calcular (por dupla)

Todas calculadas **após** deduplicação, em ordem cronológica por `DataHora`.

| Coluna                          | Lógica                                                                 |
|---------------------------------|------------------------------------------------------------------------|
| `Dupla`                         | Nome normalizado (A vs B ordenado alfabeticamente)                    |
| `Ligas`                         | Torneios únicos na ordem de aparição, separados por ` / `             |
| `Quantidade de entradas`        | Total de linhas da dupla                                               |
| `Quantidade de GREENS`          | Count de resultados GREEN                                              |
| `Percentual de GREEN (%)`       | GREENs / Total × 100                                                  |
| `Pontuação (+1/–3)`             | Soma de +1 por GREEN e -3 por RED                                     |
| `Últimos 6 jogos (G/R)`         | 6 jogos com maior DataHora → ex: `"G-R-G-G-R-G"`                     |
| `%Green últimos 10`             | % GREEN nos últimos 10 jogos (ou menos se < 10)                       |
| `Quantidade de REDS`            | Count de resultados RED                                                |
| `Sequencia máxima de Reds`      | Maior streak de REDs consecutivos                                     |
| `Reds após Red`                 | Qtd de vezes que RED foi seguido por outro RED no mesmo dia           |
| `SISTEMA RED (%)`               | (Reds após Red no mesmo dia / Total de Reds) × 100                   |
| `SRPT`                          | Score Recente Ponderado por Tempo (ver fórmula abaixo)                |
| `Sequência Atual G`             | Greens consecutivos no final da sequência cronológica                 |
| `Sequencia máxima de Greens`    | Maior streak de GREENs consecutivos                                   |
| `Lucro/Prejuízo TOTAL`          | Soma da coluna `Lucro/Prej.` de todas as partidas da dupla           |

### Fórmula SRPT

```python
# Para cada dupla, ordenada por DataHora (mais antigo → mais recente)
# Posição do último jogo = N-1 (índice 0-based do último)

for i, jogo in enumerate(jogos_ordenados):
    distancia = (N - 1) - i          # 0 para o último, 1 para o anterior...
    peso = 0.5 ** (distancia / 10)   # meia-vida de 10 jogos
    valor = +1 if jogo == 'Green' else -3

SRPT = sum(peso * valor for cada jogo)
```

---

## API Backend

### `POST /analyze`

**Input:** multipart/form-data com um ou mais arquivos `.xlsx`

**Output:** JSON com lista de duplas e suas métricas

```json
{
  "total_jogos_brutos": 16163,
  "total_jogos_apos_dedup": 12847,
  "duplas": [
    {
      "dupla": "Agent vs Force",
      "ligas": "Liga A / Liga B",
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

---

## Frontend — Funcionalidades

### Tela Principal
1. **Upload Zone** — drag & drop ou clique para selecionar múltiplos `.xlsx`
2. **Botão Analisar** — dispara `POST /analyze`
3. **Tabela de Resultados** com:
   - Todas as colunas da análise
   - Ordenação por qualquer coluna
   - Filtros: % Green mínimo, SRPT mínimo, Ligas
   - Highlight: verde para GREEN alto, vermelho para RED alto
   - Exportar resultado como `.xlsx`

### Visual
- Dark theme (estética tech — alinhado com BetChecker)
- Cores: verde para bons indicadores, vermelho para ruins, cinza para neutro

---

## Validações e Edge Cases

- Arquivo sem aba `Tips Enviadas` → erro com mensagem clara
- Duplas com sufixos misturados `(2x6)` → normalizar antes de deduplicar
- Coluna `Hora` como objeto time ou string → normalizar para `HH:MM:SS`
- Coluna `Data` como datetime ou string → normalizar para `YYYY-MM-DD`
- `Lucro/Prej.` com vírgula decimal (padrão BR) → converter para float
- Dupla com < 6 jogos após dedup → excluir do resultado
- Dupla com < 35% GREEN após dedup → excluir do resultado

---

## Fluxo de Implementação Sugerido

```
Sprint 1 (Dia 1-2): Backend Core
  - loader.py: leitura de múltiplos .xlsx
  - normalizer.py: normalização de nomes de duplas
  - deduplicator.py: cluster ≤ 5 min
  - Testes unitários de deduplicação com os arquivos reais

Sprint 2 (Dia 3-4): Métricas + API
  - metrics.py: todas as 16 métricas
  - FastAPI endpoint /analyze
  - Validações e tratamento de erros

Sprint 3 (Dia 5-6): Frontend
  - Upload + chamada à API
  - Tabela com TanStack Table
  - Filtros e ordenação
  - Dark theme

Sprint 4 (Dia 7): Deploy + Entrega
  - Docker Compose
  - Testes com planilhas reais do cliente
  - Ajustes finais
```

---

## Observações para o Cursor

- **Não alterar** nenhuma lógica de negócio sem instrução explícita
- **Não inventar** dados — apenas processar o que existe nas planilhas
- A deduplicação é uma função pura e isolada — não misturar com cálculo de métricas
- Sempre ordenar cronologicamente por `DataHora` antes de calcular sequências
- `Últimos 6` = os 6 registros com **maior** DataHora após toda a dedup

---

## Arquivos de Referência

- `prompt_cliente.txt` — prompt completo com todas as regras de negócio
- `Bot_287805_*.xlsx` — planilha de exemplo (365)
- `Bot_286787_*.xlsx` — planilha de exemplo (Betano)
- Ambas têm 26 colunas, aba `Tips Enviadas`, ~6k-9k linhas