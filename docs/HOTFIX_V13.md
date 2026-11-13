# Dealer Hub Autovema — Correção de navegação V13

## Falhas corrigidas

A suíte completa da V12 apresentou 4 falhas em `tests/test_sidebar_navigation.py`:

- Três testes falharam porque o mock `FakeStreamlit` não implementava `st.empty()`, que é API válida da aplicação Streamlit.
- Um teste identificou que `render_main_navigation` existia em `src/ui.py` mas não era utilizado no fluxo autenticado de `app.py`.

A V13 importa e chama `render_main_navigation(nav, selected)` após a navegação lateral,
sem ampliar permissões nem mudar o controle de acesso. O mock ganha o método `empty`.

Esta entrega também inclui todo o pacote V12: correção do ImportError, CRUD de códigos
SIGMEC, desativação de códigos padrão, sincronização de OS e testes do domínio.

## Validação antes do PR

- Compilação: `python -m compileall -q app.py src tests`
- Testes completos: `python -m pytest -q`
- Git: `git diff --cached --check`

Se a suíte falhar, a automação interrompe antes de `git push`.

## Segurança

- Não altera `.env`, Secrets, backups ou credenciais.
- Não conecta no MongoDB durante a atualização do código.
- Não reatribui bônus de recompra durante a sincronização SIGMEC.
- As regras de acesso às páginas continuam determinadas por `nav` filtrada com `can`.

## Depois do merge

Acesse Configurações do Programa e confira o catálogo SIGMEC. A sincronização de OS
é manual e deve ser realizada após avaliar os códigos adicionados ou modificados.
