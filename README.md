# MenuFlow integrado — protótipo multi-restaurante

Este pacote une a estrutura de cadastro/login multi-perfil com módulos administrativos de restaurante.

## Perfis
- **Suporte:** analisa/aprova/suspende restaurantes e consulta usuários.
- **Restaurante:** cardápio, pedidos, estoque, movimentações, equipe e financeiro. Todas as consultas/mutações são limitadas ao `restaurant_id` autenticado.
- **Cliente:** conta individual, lista restaurantes aprovados, escolhe cardápio, personaliza itens, envia pedidos e consulta seus pedidos.

## Rodar localmente
1. Instale Python 3.10+.
2. `pip install -r requirements.txt`
3. `uvicorn main:app --reload`
4. Abra `http://127.0.0.1:8000`.

O banco SQLite `menuflow.db` é criado automaticamente no primeiro início. O suporte inicial é provisionado por variáveis `MENUFLOW_SUPPORT_EMAIL` e `MENUFLOW_SUPPORT_PASSWORD`. Se não definidas, o protótipo usa `support@menuflow.local` e `ChangeMe-2026!` — altere essas variáveis antes de publicar.

## Render
- Root Directory: vazio (raiz do repositório, onde estão `main.py` e `requirements.txt`)
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Persistência:** esta versão usa SQLite. Em hospedagem com filesystem efêmero, os dados podem desaparecer ao redeploy/reinício. Para uso real, migre para PostgreSQL e configure backups; o banco SQLite não deve ser considerado persistente no Render sem disco persistente.

**Antes de produção:** configurar suporte com senha forte e segredo fora do código; implementar recuperação de senha, rate limiting, HTTPS, proteção adicional contra CSRF conforme fluxo, auditoria, backups, integração de pagamento e testes de isolamento. O protótipo não processa pagamento real.
