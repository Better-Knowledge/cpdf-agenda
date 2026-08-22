import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import crypto, render
from ..auth import Chamador, chamador_atual
from ..config import settings
from ..db import get_db
from ..drivers.base import ErroDriver
from ..drivers.registry import obter_driver
from ..errors import ApiError
from ..models import ChannelConfig, ChannelMessage, ChannelOptout, ChannelTemplate
from ..schemas import ConfigIn, EnviarIn, EnviarOut, MensagemOut, TemplateIn, TemplateOut

router = APIRouter(tags=["canal"])


def _config(db: Session, org_id) -> ChannelConfig:
    config = db.get(ChannelConfig, org_id)
    if config is None or not config.ativo:
        raise ApiError(
            code="CANAL_NAO_CONFIGURADO",
            message="A organização não tem canal de WhatsApp configurado.",
            hint="Configure driver, número dedicado e credenciais em POST /canal/config.",
            status_code=409,
        )
    return config


def _sessao_aberta(db: Session, org_id, telefone: str) -> bool:
    """Janela de sessão: houve inbound deste telefone nas últimas 24h."""
    limite = func.now() - timedelta(hours=settings().sessao_horas)
    return (
        db.scalar(
            select(func.count())
            .select_from(ChannelMessage)
            .where(
                ChannelMessage.org_id == org_id,
                ChannelMessage.telefone == telefone,
                ChannelMessage.direcao == "entrada",
                ChannelMessage.created_at >= limite,
            )
        )
        > 0
    )


@router.post(
    "/canal/enviar",
    response_model=EnviarOut,
    summary="Envia mensagem de WhatsApp (sessão ou template)",
    description=(
        "Template-first: mensagem ativa (fora da janela de 24h de uma conversa aberta "
        "pelo cliente) é SEMPRE template — tipo=sessao é recusado nesse caso. Envio "
        "ativo consulta o opt-out antes, sempre. Aceita Idempotency-Key."
    ),
)
def enviar(
    dados: EnviarIn,
    request: Request,
    chamador: Chamador = Depends(chamador_atual),
    db: Session = Depends(get_db),
) -> EnviarOut:
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        repetida = db.scalar(
            select(ChannelMessage).where(
                ChannelMessage.org_id == chamador.org_id,
                ChannelMessage.idempotency_key == idem_key,
            )
        )
        if repetida:
            return EnviarOut(
                message_id=repetida.id,
                status=repetida.status,
                corpo_renderizado=repetida.corpo_renderizado or "",
            )

    config = _config(db, chamador.org_id)
    sessao_aberta = _sessao_aberta(db, chamador.org_id, dados.destinatario)

    if dados.tipo == "sessao":
        # Regra template-first (RF-10): mensagem ativa recusa tipo=sessao.
        if not sessao_aberta:
            raise ApiError(
                code="MENSAGEM_ATIVA_EXIGE_TEMPLATE",
                message=(
                    "Não há conversa aberta com este cliente nas últimas "
                    f"{settings().sessao_horas}h — isto é mensagem ativa."
                ),
                hint="Reenvie com tipo=template e o template_nome adequado (ex.: lembrete_24h).",
                status_code=409,
            )
        if not dados.texto:
            raise ApiError(
                code="TEXTO_OBRIGATORIO",
                message="tipo=sessao exige o campo texto.",
                hint="Envie o texto da resposta, ou use tipo=template.",
            )
        corpo = dados.texto
        template = None
    else:
        # Envio ativo consulta o opt-out SEMPRE.
        if db.get(ChannelOptout, (chamador.org_id, dados.destinatario)):
            raise ApiError(
                code="OPTOUT_ATIVO",
                message="Este cliente pediu para não receber mensagens ativas.",
                hint=(
                    "Não tente outro canal automático — crie uma tarefa para contato "
                    "humano se o assunto for importante."
                ),
                status_code=403,
            )
        q = select(ChannelTemplate).where(
            ChannelTemplate.org_id == chamador.org_id, ChannelTemplate.ativo
        )
        if dados.template_id:
            q = q.where(ChannelTemplate.id == dados.template_id)
        elif dados.template_nome:
            q = q.where(ChannelTemplate.nome == dados.template_nome)
        else:
            raise ApiError(
                code="TEMPLATE_OBRIGATORIO",
                message="tipo=template exige template_nome ou template_id.",
                hint="Liste os templates em GET /canal/templates.",
            )
        template = db.scalars(q.order_by(ChannelTemplate.versao.desc())).first()
        if template is None:
            # IA-02: sem template aprovado, mensagem não sai (+ tarefa para humano)
            raise ApiError(
                code="TEMPLATE_INEXISTENTE",
                message="Não há template ativo com esse nome para a organização.",
                hint=(
                    "A mensagem NÃO foi enviada. Cadastre/aprove o template em "
                    "POST /canal/templates e crie uma tarefa para o humano revisar."
                ),
                status_code=409,
            )
        corpo = render.renderizar(template.corpo, dados.variaveis)

    mensagem = ChannelMessage(
        org_id=chamador.org_id,
        direcao="saida",
        telefone=dados.destinatario,
        tipo=dados.tipo,
        template_id=template.id if template else None,
        corpo_renderizado=corpo,
        driver=config.driver,
        idempotency_key=idem_key,
    )
    db.add(mensagem)
    db.flush()

    driver = obter_driver(config.driver)
    credenciais = crypto.decifrar(config.credenciais)
    try:
        if dados.tipo == "template" and not driver.suporta_texto_livre_ativo:
            resultado = driver.enviar_template_oficial(
                credenciais, dados.destinatario, template.nome, dados.variaveis
            )
        else:
            resultado = driver.enviar_texto(credenciais, dados.destinatario, corpo)
        mensagem.status = "enviada"
        mensagem.driver_message_id = resultado.driver_message_id
        mensagem.custo = resultado.custo
    except ErroDriver as e:
        mensagem.status = "falha"
        mensagem.erro = str(e)
        db.commit()
        raise ApiError(
            code="FALHA_NO_DRIVER",
            message=f"O driver {config.driver} não entregou a mensagem.",
            hint="Falha registrada em channel_messages; retry é seguro (idempotente).",
            retryable=e.retryable,
            status_code=502,
        ) from e
    db.commit()
    return EnviarOut(message_id=mensagem.id, status=mensagem.status, corpo_renderizado=corpo)


@router.get("/canal/templates", response_model=list[TemplateOut], summary="Templates da organização")
def listar_templates(
    chamador: Chamador = Depends(chamador_atual),
    db: Session = Depends(get_db),
) -> list[TemplateOut]:
    linhas = db.scalars(
        select(ChannelTemplate)
        .where(ChannelTemplate.org_id == chamador.org_id, ChannelTemplate.ativo)
        .order_by(ChannelTemplate.nome, ChannelTemplate.versao.desc())
    ).all()
    return [TemplateOut.model_validate(t, from_attributes=True) for t in linhas]


@router.post(
    "/canal/templates",
    response_model=TemplateOut,
    status_code=201,
    summary="Cadastra (ou versiona) um template de mensagem ativa",
    description=(
        "Mesmo nome → nova versão. O texto é redigido uma vez, revisado por humano e "
        "versionado (IA-02) — a IA não improvisa mensagem ativa por cliente."
    ),
)
def criar_template(
    dados: TemplateIn,
    chamador: Chamador = Depends(chamador_atual),
    db: Session = Depends(get_db),
) -> TemplateOut:
    ultima_versao = (
        db.scalar(
            select(func.max(ChannelTemplate.versao)).where(
                ChannelTemplate.org_id == chamador.org_id, ChannelTemplate.nome == dados.nome
            )
        )
        or 0
    )
    template = ChannelTemplate(
        org_id=chamador.org_id, versao=ultima_versao + 1, **dados.model_dump()
    )
    db.add(template)
    db.commit()
    return TemplateOut.model_validate(template, from_attributes=True)


@router.get("/canal/mensagens", response_model=list[MensagemOut], summary="Histórico por telefone")
def listar_mensagens(
    telefone: str = Query(),
    limit: int = Query(default=20, le=100),
    chamador: Chamador = Depends(chamador_atual),
    db: Session = Depends(get_db),
) -> list[MensagemOut]:
    linhas = db.scalars(
        select(ChannelMessage)
        .where(ChannelMessage.org_id == chamador.org_id, ChannelMessage.telefone == telefone)
        .order_by(ChannelMessage.created_at.desc())
        .limit(limit)
    ).all()
    return [
        MensagemOut(
            id=m.id,
            direcao=m.direcao,
            telefone=m.telefone,
            tipo=m.tipo,
            corpo_renderizado=m.corpo_renderizado,
            driver=m.driver,
            status=m.status,
            erro=m.erro,
            created_at=m.created_at.isoformat(),
        )
        for m in linhas
    ]


@router.post(
    "/canal/config",
    status_code=201,
    summary="Configura o driver da organização (write-only)",
    description=(
        "Trocar de driver é só trocar esta configuração — nenhum módulo muda. "
        "Credenciais são cifradas e NUNCA voltam em resposta ou log. O produto recusa "
        "número que não seja dedicado."
    ),
)
def configurar(
    dados: ConfigIn,
    chamador: Chamador = Depends(chamador_atual),
    db: Session = Depends(get_db),
) -> dict:
    if not dados.confirmo_numero_dedicado:
        raise ApiError(
            code="NUMERO_PESSOAL_RECUSADO",
            message="O canal exige um número de WhatsApp dedicado à organização.",
            hint=(
                "Não use o número pessoal: drivers não-oficiais podem ser banidos pelo "
                "WhatsApp. Provisione um chip/número próprio e confirme com "
                "confirmo_numero_dedicado=true."
            ),
        )
    config = db.get(ChannelConfig, chamador.org_id)
    cifradas = crypto.cifrar(dados.credenciais)
    if config is None:
        config = ChannelConfig(org_id=chamador.org_id)
        db.add(config)
    config.driver = dados.driver
    config.numero = dados.numero
    config.instancia = dados.instancia
    config.credenciais = cifradas
    # Segredo do webhook (PRD §9): rotacionado a cada reconfiguração. Aparece
    # UMA vez, aqui — é o que o aluno cola no painel do driver.
    config.webhook_token = secrets.token_urlsafe(24)
    config.ativo = True
    db.commit()
    return {
        "driver": config.driver,
        "numero": config.numero,
        "ativo": True,
        "webhook_url": f"/webhooks/canal/{config.driver}?token={config.webhook_token}",
    }
