// A UI é o segundo cliente da API (PRD §12): toda ação daqui existe antes
// como rota autenticada — deletar a UI não remove capacidade nenhuma.
// Fase 1 do conector: chave de acesso (X-Agent-Key) guardada no navegador.

export interface ErroApi {
  code: string;
  message: string;
  hint: string;
  retryable: boolean;
  alternativas?: { inicio: string; label_humano: string }[];
  confirmation_token?: string; // padrão propor → confirmar (cancelamento)
  previa?: Record<string, string>;
}

export class ApiError extends Error {
  constructor(public erro: ErroApi, public status: number) {
    super(erro.message);
  }
}

const CHAVE = "agenda.chave";

export const sessao = {
  chave: () => localStorage.getItem(CHAVE),
  entrar: (chave: string) => localStorage.setItem(CHAVE, chave),
  sair: () => localStorage.removeItem(CHAVE),
};

async function chamar<T>(metodo: string, rota: string, corpo?: unknown): Promise<T> {
  const cabecalhos: Record<string, string> = { "X-Agent-Key": sessao.chave() ?? "" };
  if (corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
  if (metodo !== "GET") cabecalhos["Idempotency-Key"] = crypto.randomUUID();
  const resposta = await fetch(rota, {
    method: metodo,
    headers: cabecalhos,
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (resposta.status === 401) {
    sessao.sair();
    window.location.href = `${import.meta.env.BASE_URL}entrar`;
  }
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new ApiError(
      {
        ...dados, // preserva campos extras (alternativas, confirmation_token, prévia)
        code: dados.code ?? "ERRO",
        message: dados.message ?? "A API respondeu com erro.",
        hint: dados.hint ?? "",
        retryable: dados.retryable ?? false,
      },
      resposta.status,
    );
  }
  return dados as T;
}

export const api = {
  get: <T>(rota: string) => chamar<T>("GET", rota),
  post: <T>(rota: string, corpo?: unknown) => chamar<T>("POST", rota, corpo),
  patch: <T>(rota: string, corpo: unknown) => chamar<T>("PATCH", rota, corpo),
  put: <T>(rota: string, corpo: unknown) => chamar<T>("PUT", rota, corpo),
  delete: <T>(rota: string) => chamar<T>("DELETE", rota),
};

// ── Tipos do contrato (espelham o /openapi.json) ────────────────────────────

export interface Servico {
  id: string;
  nome: string;
  duracao_min: number;
  preco: string;
  buffer_antes_min: number;
  buffer_depois_min: number;
  ativo: boolean;
}

export interface Recurso {
  id: string;
  nome: string;
  tipo: string | null;
  ativo: boolean;
}

export interface Compromisso {
  id: string;
  service_id: string;
  resource_id: string;
  cliente_nome: string;
  cliente_telefone: string;
  inicio: string;
  fim: string;
  label_humano: string;
  status: "agendado" | "confirmado" | "cancelado" | "realizado" | "no_show";
  origem: string;
  risco_no_show: string | null;
  risco_detalhe: { pontos: number; explicacao: string; fatores: FatorRisco[] } | null;
  observacoes: string | null;
  series_id: string | null;
}

export interface FatorRisco {
  fator: string;
  pontos: number;
  detalhe: string;
}

export interface Slot {
  inicio: string;
  fim: string;
  resource_id: string;
  label_humano: string;
}

export interface Regra {
  id: string;
  resource_id: string;
  dia_semana: number;
  hora_inicio: string;
  hora_fim: string;
}

export interface Bloqueio {
  id: string;
  resource_id: string;
  inicio: string;
  fim: string;
  motivo: string | null;
}

export interface FilaEntrada {
  id: string;
  service_id: string;
  resource_id: string | null;
  cliente_nome: string;
  cliente_telefone: string;
  janela_inicio: string;
  janela_fim: string;
  janela_humana: string;
  status: "aguardando" | "ofertado" | "aceito" | "expirado" | "cancelado";
  posicao: number | null;
  expira_em: string | null;
  slot_ofertado: string | null;
  avisos: string[];
}

export interface CanalConfig {
  configurado: boolean;
  driver: string | null;
  numero: string | null;
  instancia: string | null;
  ativo: boolean;
  webhook_url: string | null;
}

export interface CanalConexao {
  estado: "conectado" | "aguardando_qr" | "desconectado" | "desconhecido";
  qr_base64: string | null;
  detalhe: string | null;
}

export interface CanalTemplate {
  id: string;
  nome: string;
  corpo: string;
  versao: number;
  aprovado_meta: boolean;
  ativo: boolean;
}

export interface CanalOptout {
  telefone: string;
  origem: string | null;
  em: string;
}

export interface QuemSou {
  org_id: string;
  nome: string;
  papel: string | null;
  ator: "humano" | "agente";
  escopos: string[];
  titular: string | null;
}

export interface Credencial {
  id: string;
  nome: string;
  papel: "atendimento" | "operacao" | "administrativo";
  escopos: string[];
  prefixo: string;
  ativo: boolean;
  criada_em: string;
  ultimo_uso_em: string | null;
  revogada_em: string | null;
}

/** O token em claro só existe nesta resposta — o banco guarda o SHA-256. */
export interface CredencialCriada extends Credencial {
  token: string;
}

export interface Historico {
  acao: string;
  de: string | null;
  para: string | null;
  origem: string | null;
  motivo: string | null;
  em: string;
}

// ── Tempo: a borda é sempre America/Sao_Paulo (invariante do módulo) ────────

const FUSO = "America/Sao_Paulo";

export function horaLocal(iso: string): { h: number; m: number } {
  const partes = new Intl.DateTimeFormat("pt-BR", {
    timeZone: FUSO,
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const pegar = (tipo: string) => Number(partes.find((p) => p.type === tipo)?.value ?? 0);
  return { h: pegar("hour"), m: pegar("minute") };
}

export function hojeISO(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO }).format(new Date());
}

export function dataPorExtenso(dataISO: string): string {
  const texto = new Intl.DateTimeFormat("pt-BR", {
    timeZone: FUSO,
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(`${dataISO}T12:00:00-03:00`));
  return texto.charAt(0).toUpperCase() + texto.slice(1); // só a inicial
}

export function mudarDia(dataISO: string, dias: number): string {
  const d = new Date(`${dataISO}T12:00:00-03:00`);
  d.setDate(d.getDate() + dias);
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO }).format(d);
}

// ── Integrações de calendário e link público (etapa 8) ──────────────────────

export interface FeedIcs {
  id: string;
  resource_id: string | null;
  modo: "completo" | "privado";
  url: string; // redigida
  revogado_em: string | null;
  created_at: string;
}

export interface FeedIcsCriado extends FeedIcs {
  url_completa: string;
}

export interface ConexaoGoogle {
  resource_id: string;
  resource_nome: string;
  calendar_id: string;
  ativo: boolean;
  precisa_reconectar: boolean;
  conectado_em: string;
}

export interface ConfigCalendly {
  service_id: string;
  resource_id: string;
  cria_lembretes: boolean;
  ativo: boolean;
  webhook_url: string;
  created_at: string;
}

export interface LinkPublico {
  id: string;
  service_id: string;
  resource_id: string | null;
  slug: string;
  url: string;
  ativo: boolean;
  exige_caucao: boolean;
  valor_caucao: string | null;
  created_at: string;
}

export interface PaginaPublica {
  slug: string;
  servico: string;
  duracao_min: number;
  preco: string;
  exige_caucao: boolean;
  valor_caucao: string | null;
  aviso_caucao: string | null;
}

export interface AgendamentoPublico {
  id: string;
  servico: string;
  inicio: string;
  label_humano: string;
  mensagem: string;
}

/** Cliente das rotas públicas (P-01): **sem** chave de acesso.
 *
 * Mandar a credencial do prestador de dentro da página que o cliente final
 * abre seria vazá-la para quem tem o link. A página pública é anônima de
 * propósito — e a API a trata como tal, com limite por IP. */
async function chamarPublico<T>(metodo: string, rota: string, corpo?: unknown): Promise<T> {
  const resposta = await fetch(rota, {
    method: metodo,
    headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new ApiError(
      {
        ...dados,
        code: dados.code ?? "ERRO",
        message: dados.message ?? "Não foi possível falar com a agenda.",
        hint: dados.hint ?? "",
        retryable: dados.retryable ?? false,
      },
      resposta.status,
    );
  }
  return dados as T;
}

export const publico = {
  get: <T>(rota: string) => chamarPublico<T>("GET", rota),
  post: <T>(rota: string, corpo: unknown) => chamarPublico<T>("POST", rota, corpo),
};

export interface Metricas {
  de: string;
  ate: string;
  total: number;
  por_status: Record<string, number>;
  por_origem: Record<string, number>;
  pct_por_conversa: number | null;
  pct_no_show: number | null;
  pct_confirmados: number | null;
  pct_ocupacao: number | null;
  cancelados: number;
  fila_aguardando: number;
  fila_atendida: number;
  narrativa: string;
}
