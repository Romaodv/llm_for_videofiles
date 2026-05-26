# Local Knowledge Explorer

MVP local-first para transcrever videos com Whisper, gerar SRT com timestamps, indexar chunks em SQLite e consultar via RAG com fontes clicaveis.

## O que existe agora

- Selecao manual de video pelos arquivos locais.
- Botao explicito de indexacao/reindexacao.
- Transcricao com `faster-whisper` usando modelo `small` por padrao.
- SRT salvo em `.local_data/transcripts/`.
- SQLite local em `.local_data/app.sqlite3`.
- Embeddings locais por hashing, sem custo e sem rede, com opcao Ollama.
- Retrieve local top-k por cosine similarity dentro do backend.
- Chat Cloud via DeepSeek com memoria curta da sessao.
- Fontes com nome do arquivo, timestamps e salto direto para o trecho do video.
- Topicos navegaveis, com sumarizacao por LLM quando configurada e fallback local.
- Biblioteca persistente: videos indexados ficam salvos no SQLite com embeddings, SRT, chunks, topicos, categoria e notas.
- Barra lateral agrupada por categoria para reabrir videos sem transcrever/indexar novamente.
- Painel de progresso em tempo real para indexacao: validacao, hash, Whisper, SRT, chunking, embeddings, SQLite e topicos.
- Conversao opcional para MP4 H.264/AAC quando o navegador toca audio mas nao mostra imagem do video.
- Topicos gerados por LLM local via Ollama, em blocos de transcript com timestamps.
- Busca textual basica no SRT carregado, com salto para o timestamp encontrado.


## Portable launcher

Para rodar o app com uma tela de inicializacao local:

```bash
./start.sh
```

No Windows, use:

```bat
start.bat
```

Isso abre uma landing em `localhost`. Ao clicar em `Start app`, o launcher:

- cria/usa um virtualenv local em `.venv` para evitar o bloqueio PEP 668 do Python do sistema;
- instala dependencias Python do projeto dentro desse virtualenv;
- verifica/instala Ollama no Linux quando possivel;
- inicia `ollama serve` em background;
- baixa o modelo `qwen2.5:3b` se ainda nao existir;
- garante que o frontend esta buildado;
- inicia o backend FastAPI;
- abre o app em `http://127.0.0.1:8000`.

Observacao: instalacao automatica do Ollama pode exigir permissao de administrador/sudo. Em Windows ou ambientes sem permissao, instale o Ollama manualmente antes de iniciar o launcher. Em Ubuntu/Debian, se a criacao do virtualenv falhar, instale `python3-venv`: `sudo apt install python3-venv`.

### Gerar pacote portatil

Em uma maquina de build com Node/NPM disponivel:

```bash
python scripts/build_portable.py
```

O pacote sai em:

```text
dist/llm-forfiles-portable
```

Essa pasta inclui o backend, frontend buildado, landing launcher e scripts `start.sh`/`start.bat`. Ela nao inclui `node_modules`, `.local_data`, modelos Ollama nem videos indexados. Na primeira execucao no outro PC, o launcher prepara dependencias e baixa o modelo local quando necessario.

## Backend

Instale dependencias:

```bash
python -m pip install -e .
```

Inicie a API:

```bash
python -m uvicorn backend.app.main:app --reload
```

Healthcheck:

```text
GET http://127.0.0.1:8000/health
```

Endpoints principais:

- `GET /files/list?path=...`
- `POST /videos/index`
- `POST /videos/index/jobs`
- `GET /jobs/{job_id}`
- `GET /documents`
- `GET /documents/{id}/transcript`
- `PUT /documents/{id}/save`
- `GET /documents/{id}/topics`
- `GET /documents/{id}/media`
- `POST /documents/{id}/media/jobs`
- `POST /documents/{id}/topics/summarize`
- `POST /search/semantic`
- `POST /search/ask`
- `GET /settings/secrets/deepseek`
- `POST /settings/secrets/deepseek`
- `DELETE /settings/secrets/deepseek`
- `GET /media?path=...`

## Frontend

O frontend fica em `frontend/`.

```bash
cd frontend
npm install
npm run dev
```

Se precisar apontar para outra API:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Providers

Padrao sem custo:

```bash
EMBEDDING_PROVIDER=hashing
```

Embeddings locais via Ollama:

```bash
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

Chat externo via DeepSeek:

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
```

Topicos locais via Ollama:

```bash
LLM_PROVIDER=ollama
OLLAMA_LLM_MODEL=qwen2.5:3b
OLLAMA_TOPIC_MODEL=qwen2.5:3b
```

Whisper:

```bash
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Observacao: `faster-whisper` baixa o modelo na primeira transcricao e precisa de acesso ao cache/modelo do Hugging Face. O processamento de video tambem depende de suporte de media/ffmpeg via PyAV.

## Fluxo

1. Abra a UI.
2. Navegue ate um video local ou cole o caminho absoluto.
3. Informe uma categoria e clique em Indexar.
4. A aplicacao mostra progresso detalhado enquanto transcreve, salva SRT, cria chunks, calcula embeddings e grava tudo no SQLite.
5. Use Salvar para alterar categoria/notas sem reprocessar o video.
6. Reabra qualquer video pela barra lateral categorizada; os dados salvos sao reaproveitados.
7. Se o video tocar apenas audio, clique em `MP4` ou `Gerar MP4 H.264` para criar uma copia web em `.local_data/web_videos/`.
8. Use topicos, SRT ou respostas do chat para pular para o trecho do video.

## Chat Cloud

A UI usa apenas o modo Cloud no chat, com DeepSeek. A memoria curta nao e persistida no banco; a UI envia somente as ultimas mensagens da sessao atual junto da pergunta.

A DeepSeek API key pode ser informada na UI e salva localmente. Quando salva, o backend grava o segredo criptografado em `.local_data/secrets.json` usando uma chave Fernet em `.local_data/secret.key`, ambos com permissao de dono quando o sistema permite. A UI mostra apenas o status e a chave mascarada, nunca a chave completa. Tambem ha botao `Apagar API_KEY` para remover a chave salva.

Observacao de seguranca: isso protege contra gravacao em texto puro, mas quem tiver acesso aos dois arquivos locais (`secrets.json` e `secret.key`) consegue descriptografar. Para seguranca mais forte, use `DEEPSEEK_API_KEY` via variavel de ambiente ou um keyring do sistema operacional.

Para gerar topicos locais com Ollama:

```bash
ollama pull qwen2.5:3b
OLLAMA_TOPIC_MODEL=qwen2.5:3b python -m uvicorn backend.app.main:app --reload
```

Para usar o chat Cloud:

```bash
DEEPSEEK_API_KEY=... python -m uvicorn backend.app.main:app --reload
```

Os topicos do video usam o provider local de topicos (`OLLAMA_TOPIC_MODEL`) para manter essa parte local-first.
