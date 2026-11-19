# Agenda de publicações · Rosa Brand Studio

Publica automaticamente no Instagram (@rosabrandstudio) os posts aprovados em `agenda.json`.

- **Como funciona:** a cada 15 minutos o GitHub Actions roda `tools/publicar.py`, que publica o que já chegou no horário e grava o resultado na própria agenda (`status`, `link`).
- **Mídia:** fica em `docs/m/` e é servida pelo GitHub Pages, porque a Meta baixa os arquivos por link público.
- **Token:** fica só em *Settings → Secrets → Actions → `IG_TOKEN`*. Nunca em arquivo ou commit. Validade de 60 dias.

## Status de cada post
| status | significado |
|---|---|
| `agendado` | vai sair no horário de `at` |
| `publicado` | saiu; o link está em `link` |
| `aguardando_decisao` | data já passou antes da automação existir; não sai sozinho |
| `atrasado` | passou mais de 12h do horário sem sair; não sai sozinho |
| `erro` | falhou 3 vezes; detalhe em `erro` |

Para remarcar: mude `at` (formato `2026-12-03T12:00:00-03:00`) e deixe `status` como `agendado`.
Para cancelar: troque `status` para `cancelado`.

## Teste sem publicar
Actions → *Publicar no Instagram* → *Run workflow* → modo `teste`.
