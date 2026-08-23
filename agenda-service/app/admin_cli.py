"""Emissão e revogação de credenciais de agente — pela linha de comando.

**Por que não existe endpoint para isto.** Uma rota capaz de emitir credencial
administrativa é um backdoor permanente: quem a alcançar concede a si mesmo
qualquer autoridade. O bootstrap acontece onde já existe confiança — no VPS,
por quem tem acesso ao servidor. Depois disso, humanos autenticados por JWT
gerem credenciais pela tela (escopo `credenciais:admin`), e nenhum token de
agente consegue emitir outro.

Uso:
    uv run python -m app.admin_cli emitir <org_id> "Nome" administrativo
    uv run python -m app.admin_cli emitir <org_id> "Bot" atendimento --escopos agenda:read
    uv run python -m app.admin_cli listar <org_id>
    uv run python -m app.admin_cli revogar <credencial_id>
    uv run python -m app.admin_cli importar-env
"""

import sys
from uuid import UUID

from sqlalchemy import select

from .auth import ESCOPO_CREDENCIAIS, escopos_do_papel, gerar_token, hash_token, validar_escopos
from .models import AgentCredential
from .sessao import SessionLocal, sessao_worker
from .tempo import agora_utc


def emitir(org_id: UUID, nome: str, papel: str, escopos: list[str] | None = None) -> str:
    """Cria a credencial e devolve o token em claro — a única vez que ele existe."""
    autoridade = validar_escopos(escopos) if escopos else sorted(escopos_do_papel(papel))
    token, token_hash, prefixo = gerar_token()
    with SessionLocal() as db:
        sessao_worker(db)  # bootstrap: não há org no contexto ainda
        db.add(
            AgentCredential(
                org_id=org_id,
                nome=nome,
                papel=papel,
                escopos=autoridade,
                token_hash=token_hash,
                prefixo=prefixo,
            )
        )
        db.commit()
    return token


def listar(org_id: UUID) -> list[AgentCredential]:
    with SessionLocal() as db:
        sessao_worker(db)
        return list(
            db.scalars(
                select(AgentCredential)
                .where(AgentCredential.org_id == org_id)
                .order_by(AgentCredential.criada_em)
            )
        )


def revogar(credencial_id: UUID) -> bool:
    with SessionLocal() as db:
        sessao_worker(db)
        linha = db.get(AgentCredential, credencial_id)
        if linha is None:
            return False
        linha.ativo = False
        linha.revogada_em = agora_utc()
        db.commit()
    return True


def _chaves_do_ambiente() -> dict[str, str]:
    """Lê AGENT_API_KEYS direto do ambiente, e não de `Settings`.

    A diferença é o ponto da etapa: o caminho de **autenticação** deixou de
    honrar o ambiente, mas a **ferramenta de migração** ainda precisa lê-lo —
    senão quem atualiza o código perde o acesso à própria chave antes de ter
    como migrá-la, e a migração vira uma corrida contra o deploy.
    """
    import json
    import os

    bruto = os.environ.get("AGENT_API_KEYS", "").strip()
    if not bruto or bruto == "{}":
        return {}
    return json.loads(bruto)


def importar_env() -> int:
    """Migra AGENT_API_KEYS para a tabela preservando o valor da chave.

    Preservar importa: a chave que está no navegador do aluno (localStorage)
    continua funcionando, então a migração não desloga ninguém.

    A credencial nasce com `credenciais:admin` porque é o que ela já tinha —
    era autoridade total sobre a organização, e uma migração que silenciosamente
    tira poder deixa a tela de Integrações inacessível sem dizer por quê. É
    concessão explícita de quem roda o comando no servidor, que é exatamente o
    caso em que o escopo pode ser dado (nunca por preset, nunca por rota).
    """
    migradas = 0
    for chave, org in _chaves_do_ambiente().items():
        h = hash_token(chave)
        with SessionLocal() as db:
            sessao_worker(db)
            if db.scalar(select(AgentCredential).where(AgentCredential.token_hash == h)):
                continue
            db.add(
                AgentCredential(
                    org_id=UUID(org),
                    nome="Importada de AGENT_API_KEYS",
                    papel="administrativo",
                    escopos=sorted(escopos_do_papel("administrativo") | {ESCOPO_CREDENCIAIS}),
                    token_hash=h,
                    prefixo=chave[:10],
                )
            )
            db.commit()
            migradas += 1
    return migradas


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    comando, *resto = argv

    if comando == "emitir":
        if len(resto) < 3:
            print("uso: emitir <org_id> <nome> <papel> [--escopos a,b,c]")
            return 1
        org_id, nome, papel = UUID(resto[0]), resto[1], resto[2]
        escopos = None
        if "--escopos" in resto:
            escopos = resto[resto.index("--escopos") + 1].split(",")
        token = emitir(org_id, nome, papel, escopos)
        print(f"credencial criada para {nome} ({papel})")
        print(f"\n  {token}\n")
        print("Guarde agora: o token não pode ser recuperado depois.")
        if escopos and ESCOPO_CREDENCIAIS in escopos:
            print(
                "\nATENÇÃO: esta credencial pode emitir e revogar outras. Um token\n"
                "assim sobrevive à própria revogação — quem o tiver emite um novo\n"
                "antes de você derrubar o antigo. Dê só a quem administra a conta."
            )
        return 0

    if comando == "listar":
        for c in listar(UUID(resto[0])):
            estado = "revogada" if c.revogada_em else ("ativa" if c.ativo else "inativa")
            print(f"{c.id}  {c.prefixo}…  {c.papel:<15} {estado:<9} {c.nome}")
            print(f"    escopos: {', '.join(c.escopos)}")
        return 0

    if comando == "revogar":
        ok = revogar(UUID(resto[0]))
        print("revogada" if ok else "credencial não encontrada")
        return 0 if ok else 1

    if comando == "importar-env":
        quantas = importar_env()
        print(f"{quantas} credencial(is) importada(s) de AGENT_API_KEYS")
        if quantas:
            print(
                "As chaves continuam valendo com o mesmo valor — ninguém é deslogado.\n"
                "Agora remova AGENT_API_KEYS do .env: a autenticação não a lê mais."
            )
        return 0

    print(f"comando desconhecido: {comando}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
