# Dealer Hub — correções V12 (13/11/2026)

## Correção de ImportError

As páginas Clientes, Veículos, Jornada de Revisões, Fidelidade e Serviços voltam a consumir a matriz das cinco revisões em `src/revision_audit.py`, por meio de `src/revision_loader.py`. Não há dependência de `_load_audit` (removida do dashboard). O filtro por empresa é aplicado na leitura de `journeys` antes de carregar os demais registros. A consulta não atribui bônus nem altera OS.

## Catálogo SIGMEC

Em **Configurações do Programa → Códigos SIGMEC de revisões**, perfis com `settings.manage` podem pesquisar, incluir, editar, desativar e reativar os códigos. O catálogo original é preservado. A exclusão é reversível (desativação). Os códigos padrão desativados ficam registrados no MongoDB com `disabled=true`, para não serem reintroduzidos automaticamente. O código de entrega `0010A14` permanece excluído das revisões.

Ao importar uma planilha de códigos no fluxo já existente, o item é reativado explicitamente. Cada alteração individual gera registro em `audit_logs`.

## Sincronização das OS

O botão **Sincronizar OS e identificar novos códigos** reprocessa as OS já armazenadas em `sigmec_orders`, utiliza o catálogo vigente e tenta localizar vínculos ROF080 novamente. Não há necessidade de reimportar o `.001`. A sincronização atualiza os resultados por código, não modifica prêmios ou bônus e não associa automaticamente etapas quando existem códigos conflitantes, motorizações desconhecidas ou OS sem conciliação.

Eventos de evidência gerados automaticamente pelo SIGMEC cujos códigos ficaram inválidos ou mudaram de etapa deixam de comprovar a revisão, passando à conferência. **Confirmações e descartes manuais são preservados.** Caso exista evento ROF080 de outra origem, ele não é sobrescrito por um novo código SIGMEC.

**Atenção:** a sincronização atualiza as evidências e a análise, não altera retroativamente registros de revisões concluídas manualmente nem calcula bônus. É necessário revisar as pendências na Jornada de Revisões.

## Testes

Execute `python -m pytest -q` e, antes de mesclar, `python -m compileall -q app.py src tests`. O instalador PowerShell automatiza ambos, abre PR e só executa o merge quando os testes locais e as verificações de CI disponíveis estiverem aprovados.
