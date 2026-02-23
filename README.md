## Dashboard eSoccer (Streamlit)

App Streamlit para analisar planilhas `.xlsx` (aba `Tips Enviadas`) e gerar métricas por dupla, seguindo as regras do `CLAUDE.md` (normalização + deduplicação por cluster ≤ 5 min antes das métricas).

### Rodar local

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### Dados
- Coloque arquivos de exemplo em `Data/` (não versionado).
