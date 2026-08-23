import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { CanalConexao, CanalConfig, CanalOptout, CanalTemplate, api } from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-09: o canal de WhatsApp — driver, QR code ao vivo, templates e opt-outs.
// A UI fala só com o agenda-service; o canal-service nunca chega ao navegador.

const ESTADO_LEGIVEL: Record<string, string> = {
  conectado: "conectado",
  aguardando_qr: "aguardando QR",
  desconectado: "desconectado",
  desconhecido: "estado desconhecido",
};

// Campos de credencial por driver — write-only: nunca voltam da API.
const CREDENCIAIS_POR_DRIVER: Record<string, { chave: string; rotulo: string; dica?: string }[]> = {
  evolution: [
    { chave: "server_url", rotulo: "URL do servidor Evolution", dica: "http://evolution_api:8080" },
    { chave: "apikey", rotulo: "API key global" },
  ],
  zapi: [
    { chave: "token", rotulo: "Token da instância" },
    { chave: "client_token", rotulo: "Client-Token da conta" },
  ],
  meta: [
    { chave: "phone_number_id", rotulo: "Phone Number ID" },
    { chave: "access_token", rotulo: "Access token" },
  ],
};

const FORM_VAZIO = {
  driver: "evolution",
  numero: "",
  instancia: "",
  credenciais: {} as Record<string, string>,
  dedicado: false,
};

export function Canal() {
  const [config, setConfig] = useState<CanalConfig | null>(null);
  const [conexao, setConexao] = useState<CanalConexao | null>(null);
  const [templates, setTemplates] = useState<CanalTemplate[]>([]);
  const [optouts, setOptouts] = useState<CanalOptout[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [ocupado, setOcupado] = useState(false);
  const [configurando, setConfigurando] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);

  const [form, setForm] = useState(FORM_VAZIO);
  const [novoTemplate, setNovoTemplate] = useState({ nome: "", corpo: "" });
  const avisar = usarToast();
  const conectadoAntes = useRef(false);

  const carregar = useCallback(async () => {
    const cfg = await api.get<CanalConfig>("/canal/config");
    setConfig(cfg);
    if (cfg.configurado) {
      setTemplates(await api.get<CanalTemplate[]>("/canal/templates"));
      setOptouts(await api.get<CanalOptout[]>("/canal/optouts"));
    }
    return cfg;
  }, []);

  useEffect(() => {
    carregar()
      .then((cfg) => {
        if (cfg.configurado) return api.get<CanalConexao>("/canal/status").then(setConexao);
      })
      .catch(setErro);
  }, [carregar]);

  // Enquanto o QR está na tela, vigia o pareamento a cada 4s.
  useEffect(() => {
    if (conexao?.estado !== "aguardando_qr") return;
    const timer = setInterval(() => {
      api
        .get<CanalConexao>("/canal/status")
        .then((s) => {
          if (s.estado === "conectado") {
            setConexao(s);
            if (!conectadoAntes.current) {
              conectadoAntes.current = true;
              avisar("WhatsApp conectado — o canal está no ar");
            }
          }
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [conexao?.estado, avisar]);

  async function agir(acao: () => Promise<unknown>, feito?: string) {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
      if (feito) avisar(feito);
      return true;
    } catch (e) {
      setErro(e);
      return false;
    } finally {
      setOcupado(false);
    }
  }

  async function salvarConfig(evento: FormEvent) {
    evento.preventDefault();
    const ok = await agir(async () => {
      const resposta = await api.post<{ webhook_url: string }>("/canal/config", {
        driver: form.driver,
        numero: form.numero,
        instancia: form.instancia,
        credenciais: form.credenciais,
        confirmo_numero_dedicado: form.dedicado,
      });
      setWebhookUrl(resposta.webhook_url);
      await carregar();
      setConexao(null);
      setConfigurando(false);
      setForm(FORM_VAZIO);
    }, "Canal configurado — agora conecte o WhatsApp");
    if (!ok) return;
  }

  function conectar() {
    agir(async () => {
      const estado = await api.post<CanalConexao>("/canal/conectar");
      setConexao(estado);
      if (estado.estado === "conectado") avisar("WhatsApp já conectado");
    });
  }

  async function criarTemplate(evento: FormEvent) {
    evento.preventDefault();
    const ok = await agir(
      () => api.post("/canal/templates", novoTemplate),
      "Template salvo — nova versão ativa",
    );
    if (ok) {
      setNovoTemplate({ nome: "", corpo: "" });
      setTemplates(await api.get<CanalTemplate[]>("/canal/templates"));
    }
  }

  const camposCredencial = CREDENCIAIS_POR_DRIVER[form.driver] ?? [];
  const mostrarForm = configurando || (config !== null && !config.configurado);

  return (
    <>
      <h1>
        Canal de <em>WhatsApp</em>
      </h1>
      <p className="subtitulo">
        Por onde a agenda conversa: lembretes saem daqui e as respostas dos clientes entram por
        aqui. Trocar de fornecedor (driver) é só reconfigurar — nada muda no resto.
      </p>
      <ErroAviso erro={erro} />

      {config?.configurado && !mostrarForm && (
        <div className="cartao" style={{ marginBottom: 20 }}>
          <h2 className="bloco">Conexão</h2>
          <dl>
            <dt>Driver</dt>
            <dd>{config.driver}</dd>
            <dt>Número</dt>
            <dd className="mono">{config.numero}</dd>
            <dt>Instância</dt>
            <dd className="mono">{config.instancia}</dd>
            <dt>Estado</dt>
            <dd>
              {conexao ? (
                <span className={`selo ${conexao.estado}`}>{ESTADO_LEGIVEL[conexao.estado]}</span>
              ) : (
                <span className="selo desconhecido">consultando…</span>
              )}
            </dd>
          </dl>

          {conexao?.estado === "aguardando_qr" && conexao.qr_base64 && (
            <div>
              <div className="qr-quadro">
                <img src={conexao.qr_base64} alt="QR code para parear o WhatsApp" />
              </div>
              <p style={{ fontSize: 14, color: "var(--fg-muted)" }}>
                No celular do número dedicado: WhatsApp → Aparelhos conectados → Conectar
                aparelho. A tela avisa sozinha quando parear.
              </p>
            </div>
          )}

          <div className="acoes">
            {conexao?.estado !== "conectado" && (
              <button className="acao primario" disabled={ocupado} onClick={conectar}>
                {ocupado ? "Conectando…" : "Conectar e gerar QR"}
              </button>
            )}
            <button className="acao" onClick={() => setConfigurando(true)}>
              Reconfigurar canal
            </button>
          </div>
        </div>
      )}

      {mostrarForm && (
        <form className="cartao" style={{ marginBottom: 20 }} onSubmit={salvarConfig}>
          <h2 className="bloco">{config?.configurado ? "Reconfigurar canal" : "Configurar canal"}</h2>
          <div className="formulario-linha">
            <label className="campo">
              Driver
              <select
                value={form.driver}
                onChange={(e) => setForm({ ...form, driver: e.target.value, credenciais: {} })}
              >
                <option value="evolution">Evolution (self-host)</option>
                <option value="zapi">Z-API (assinatura)</option>
                <option value="meta">Meta Cloud API (oficial)</option>
              </select>
            </label>
            <label className="campo">
              Número dedicado
              <input
                value={form.numero}
                onChange={(e) => setForm({ ...form, numero: e.target.value })}
                placeholder="+5511900000000"
                required
              />
            </label>
            <label className="campo">
              Instância
              <input
                value={form.instancia}
                onChange={(e) => setForm({ ...form, instancia: e.target.value })}
                placeholder="minha-org"
                required
              />
            </label>
          </div>
          <div className="formulario-linha">
            {camposCredencial.map((c) => (
              <label key={c.chave} className="campo">
                {c.rotulo}
                <input
                  type={c.chave.includes("key") || c.chave.includes("token") ? "password" : "text"}
                  value={form.credenciais[c.chave] ?? ""}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      credenciais: { ...form.credenciais, [c.chave]: e.target.value },
                    })
                  }
                  placeholder={c.dica}
                  required
                />
              </label>
            ))}
          </div>
          <p style={{ fontSize: 13, color: "var(--fg-muted)", margin: "10px 0" }}>
            As credenciais são cifradas e não aparecem de novo — nem aqui, nem em log.
          </p>
          <label style={{ display: "block", fontSize: 14, marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={form.dedicado}
              onChange={(e) => setForm({ ...form, dedicado: e.target.checked })}
            />{" "}
            Confirmo que este número é dedicado à organização — não é o meu número pessoal.
          </label>
          <button className="acao primario" disabled={ocupado || !form.dedicado}>
            {ocupado ? "Salvando…" : "Salvar configuração"}
          </button>{" "}
          {config?.configurado && (
            <button type="button" className="acao" onClick={() => setConfigurando(false)}>
              Voltar
            </button>
          )}
        </form>
      )}

      {webhookUrl && (
        <div className="cartao" style={{ marginBottom: 20 }}>
          <h2 className="bloco">Webhook do driver</h2>
          <p style={{ fontSize: 14 }}>
            Para driver com painel próprio (Z-API), cole esta URL lá. Ela carrega um segredo
            rotativo e aparece <strong>só agora</strong> — no Evolution o canal já apontou
            sozinho.
          </p>
          <code className="mono" style={{ fontSize: 13, wordBreak: "break-all" }}>
            {webhookUrl}
          </code>
        </div>
      )}

      {config?.configurado && (
        <>
          <div className="cartao" style={{ marginBottom: 20 }}>
            <h2 className="bloco">Templates de mensagem ativa</h2>
            <p style={{ fontSize: 14, color: "var(--fg-muted)" }}>
              Lembrete, confirmação e cobrança saem SEMPRE de um template — redigido uma vez,
              revisado e versionado. A IA preenche as variáveis, nunca improvisa o texto.
            </p>
            {templates.length === 0 ? (
              <div className="vazio">Nenhum template ainda — sem eles, nenhum lembrete sai.</div>
            ) : (
              <table className="lista">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Versão</th>
                    <th>Texto</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((t) => (
                    <tr key={t.id}>
                      <td className="mono">{t.nome}</td>
                      <td className="mono">v{t.versao}</td>
                      <td style={{ fontSize: 13 }}>{t.corpo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <form onSubmit={criarTemplate} style={{ marginTop: 14 }}>
              <div className="formulario-linha">
                <label className="campo">
                  Nome (mesmo nome = nova versão)
                  <input
                    value={novoTemplate.nome}
                    onChange={(e) => setNovoTemplate({ ...novoTemplate, nome: e.target.value })}
                    placeholder="lembrete_24h"
                    required
                  />
                </label>
                <label className="campo" style={{ flex: 2 }}>
                  Texto com {"{{variaveis}}"}
                  <input
                    value={novoTemplate.corpo}
                    onChange={(e) => setNovoTemplate({ ...novoTemplate, corpo: e.target.value })}
                    placeholder="Olá {{nome}}! Lembrete: {{servico}} {{data_hora}}. Responda SIM para confirmar."
                    required
                  />
                </label>
              </div>
              <button className="acao" disabled={ocupado}>
                Salvar template
              </button>
            </form>
          </div>

          <div className="cartao">
            <h2 className="bloco">Opt-outs</h2>
            <p style={{ fontSize: 14, color: "var(--fg-muted)" }}>
              Quem respondeu SAIR não recebe mais mensagem ativa — a regra é aplicada antes de
              qualquer IA. Remova apenas com pedido explícito do cliente.
            </p>
            {optouts.length === 0 ? (
              <div className="vazio">Ninguém pediu para sair — bom sinal.</div>
            ) : (
              <table className="lista">
                <thead>
                  <tr>
                    <th>Telefone</th>
                    <th>Origem</th>
                    <th>Quando</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {optouts.map((o) => (
                    <tr key={o.telefone}>
                      <td className="mono">{o.telefone}</td>
                      <td>{o.origem === "palavra_chave" ? "respondeu SAIR" : "pedido ao humano"}</td>
                      <td className="mono">
                        {new Date(o.em).toLocaleDateString("pt-BR", {
                          timeZone: "America/Sao_Paulo",
                        })}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <BotaoConfirmar
                          miudo
                          rotulo="Remover"
                          confirmacao="Cliente pediu?"
                          desabilitado={ocupado}
                          onConfirmar={() =>
                            agir(async () => {
                              await api.delete(`/canal/optouts/${encodeURIComponent(o.telefone)}`);
                              setOptouts(await api.get<CanalOptout[]>("/canal/optouts"));
                            }, "Opt-out removido — mensagens ativas voltam a sair")
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </>
  );
}
