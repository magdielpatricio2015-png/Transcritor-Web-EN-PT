# Transcritor Web EN-PT

App web em Streamlit para transcrever audio/video em ingles, traduzir para portugues e gerar arquivos TXT, SRT, Word e ZIP.

## Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Como usar

1. Envie um arquivo de audio ou video em ingles.
2. Escolha o modelo Whisper.
3. Clique em `Transcrever agora`.
4. Baixe o resultado em ZIP ou arquivos separados.

## Observacao

Transcricao consome processamento. Para uso comercial com muitos clientes, o ideal e rodar em servidor pago com controle de minutos, login e pagamento.
