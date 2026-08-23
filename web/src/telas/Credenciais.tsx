import { FormEvent, useCallback, useEffect, useState } from "react";
import { Credencial, CredencialCriada, QuemSou, api } from "../api";
import { BotaoConfirmar } from "../Confirmar";
import { ErroAviso } from "../ErroAviso";
import { usarToast } from "../Toast";

// T-11: quem tem acesso à agenda por integração, com que autoridade, e desde
// quando. Emitir e revogar acontecem aqui; o bootstrap da primeira credencial
// administrativa continua no servidor (`make credencial`), porque uma tela que
// concede autoridade a si mesma não teria como ser o começo da confiança.

const PAPEIS: { valor: Credencial["papel"]; rotulo: string; explica: string }[] = [
  {
    valor: "atendimento",
    rotulo: "Atendimento",
    explica: "Fala com um cliente por vez. Consulta e agenda — não cancela, não vê a agenda inteira.",
  },
  {
    valor: "operacao",
    rotulo: "Operação",
    explica: "Enxerga o dia inteiro, cancela e registra faltas. Não mexe no cadastro.",
  },
  {
    valor: "administrativo",
    rotulo: "Administrativo",
    explica: "Configura serviços, recursos, grade e canal. É o papel do conector MCP da equipe.",
  },
];

// `credenciais:admin` não aparece aqui de propósito: a API recusa concedê-lo
// por rota (uma credencial que emite credenciais sobrevive à própria
// revogação). Oferecer a caixa seria oferecer uma armadilha.
const ESCOPOS: { valor: string; rotulo: string }[] = [
  { valor: "agenda:read", rotulo: "Consultar catálogo, horários e o próprio compromisso" },
  { valor: "agenda:write", rotulo: "Agendar, remarcar, confirmar e entrar na fila" },
  { valor: "agenda:cancel", rotulo: "Cancelar compromisso" },
  { valor: "agenda:operacao", rotulo: "Ver a agenda inteira, a fila completa e registrar faltas" },
  { valor: "agenda:admin", rotulo: "Cadastrar serviços, recursos, grade e bloqueios" },
  { valor: "canal:admin", rotulo: "Configurar o canal de mensagens" },
];

const PRESET: Record<Credencial["papel"], string[]> = {
  atendimento: ["agenda:read", "agenda:write"],
  operacao: ["agenda:read", "agenda:write", "agenda:cancel", "agenda:operacao"],
  administrativo: [
    "agenda:read",
    "agenda:write",
    "agenda:cancel",
    "agenda:operacao",
    "agenda:admin",
    "canal:admin",
  ],
};

function quando(iso: string | null, nunca: string): string {
  if (!iso) return nunca;
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function Credenciais() {
  const [eu, setEu] = useState<QuemSou | null>(null);
  const [credenciais, setCredenciais] = useState<Credencial[] | null>(null);
  const [erro, setErro] = useState<unknown>(null);
  const [salvando, setSalvando] = useState(false);
  const [nome, setNome] = useState("");
  const [papel, setPapel] = useState<Credencial["papel"]>("atendimento");
  const [escopos, setEscopos] = useState<string[]>(PRESET.atendimento);
  const [ajustado, setAjustado] = useState(false);
  const [recemCriada, setRecemCriada] = useState<CredencialCriada | null>(null);
  const avisar = usarToast();

  const podeGerir = eu?.escopos.includes("credenciais:admin") ?? false;

  const carregar = useCallback(async () => {
    const quemSou = await api.get<QuemSou>("/credenciais/eu");
    setEu(quemSou);
    if (quemSou.escopos.includes("credenciais:admin")) {
      setCredenciais(await api.get<Credencial[]>("/credenciais"));
    }
  }, []);

  useEffect(() => {
    carregar().catch(setErro);
  }, [carregar]);

  function trocarPapel(novo: Credencial["papel"]) {
    setPapel(novo);
    setEscopos(PRESET[novo]); // trocar de papel recomeça do preset
    setAjustado(false);
  }

  function alternarEscopo(valor: string, marcado: boolean) {
    setEscopos((atuais) =>
      marcado ? [...atuais, valor] : atuais.filter((e) => e !== valor),
    );
    setAjustado(true);
  }

  async function emitir(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      const criada = await api.post<CredencialCriada>("/credenciais", {
        nome: nome.trim(),
        papel,
        ...(ajustado && { escopos }),
      });
      setRecemCriada(criada);
      setNome("");
      trocarPapel("atendimento");
      setCredenciais(await api.get<Credencial[]>("/credenciais"));
    } catch (e) {
      setErro(e);
    } finally {
      setSalvando(false);
    }
  }

  async function revogar(c: Credencial) {
    setSalvando(true);
    setErro(null);
    try {
      const { aviso } = await api.delete<{ aviso: string }>(`/credenciais/${c.id}`);
      avisar(aviso);
      setCredenciais(await api.get<Credencial[]>("/credenciais"));
    } catch (e) {
      setErro(e);
    } finally {
      setSalvando(false);
    }
  }

  if (eu && !podeGerir) {
    return (
      <>
        <h1>
          Chaves de <em>integração</em>
        </h1>
        <div className="cartao">
          <p>
            Esta chave de acesso não administra credenciais — ela tem{" "}
            <span className="mono">{eu.escopos.join(", ")}</span>.
          </p>
          <p style={{ color: "var(--fg-muted)", fontSize: 14 }}>
            Distribuir autoridade é a única coisa que não se concede por aqui: uma credencial
            capaz de emitir outra sobreviveria à própria revogação. Quem administra o servidor
            emite a primeira com <span className="mono">make credencial</span>.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>
        Chaves de <em>integração</em>
      </h1>
      <p className="subtitulo">
        Quem alcança a sua agenda por fora da tela — o bot do canal, o conector da equipe — e com
        que autoridade. Revogar derruba o acesso sem apagar o histórico.
      </p>
      <ErroAviso erro={erro} />

      {recemCriada && (
        <div className="cartao destaque" style={{ marginBottom: 20 }}>
          <h2 className="bloco">Guarde esta chave agora</h2>
          <p>
            Ela aparece <strong>uma única vez</strong>: o sistema guarda só um resumo criptográfico.
            Se perder, revogue esta e emita outra.
          </p>
          <p className="mono" style={{ wordBreak: "break-all", fontSize: 15, margin: "12px 0" }}>
            {recemCriada.token}
          </p>
          <button
            type="button"
            className="acao"
            onClick={() => {
              navigator.clipboard?.writeText(recemCriada.token);
              avisar("Chave copiada");
            }}
          >
            Copiar
          </button>{" "}
          <button type="button" className="acao primario" onClick={() => setRecemCriada(null)}>
            Já guardei
          </button>
        </div>
      )}

      <div className="cartao" style={{ marginBottom: 20 }}>
        {credenciais === null ? (
          <div className="vazio">Carregando…</div>
        ) : credenciais.length === 0 ? (
          <div className="vazio">Nenhuma integração ainda — emita a primeira abaixo.</div>
        ) : (
          <table className="lista">
            <thead>
              <tr>
                <th>Integração</th>
                <th>Papel</th>
                <th>Chave</th>
                <th>Último uso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {credenciais.map((c) => {
                const viva = c.ativo && !c.revogada_em;
                return (
                  <tr key={c.id} style={viva ? undefined : { color: "var(--fg-soft)" }}>
                    <td>
                      <strong>{c.nome}</strong>
                      <div style={{ fontSize: 12, color: "var(--fg-muted)" }}>
                        {c.escopos.join(" · ")}
                      </div>
                    </td>
                    <td>{PAPEIS.find((p) => p.valor === c.papel)?.rotulo ?? c.papel}</td>
                    <td className="mono">{c.prefixo}…</td>
                    <td className="mono">{quando(c.ultimo_uso_em, "nunca usada")}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {viva ? (
                        <BotaoConfirmar
                          miudo
                          rotulo="Revogar"
                          confirmacao="Revogar mesmo?"
                          desabilitado={salvando}
                          onConfirmar={() => revogar(c)}
                        />
                      ) : (
                        <span style={{ fontSize: 13 }}>
                          revogada em {quando(c.revogada_em, "—")}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <form className="cartao" onSubmit={emitir}>
        <h2 className="bloco">Nova integração</h2>
        <div className="formulario-linha">
          <label className="campo" style={{ flex: 2 }}>
            Como você vai reconhecer esta chave
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Bot do Telegram"
              required
            />
          </label>
          <label className="campo">
            Papel
            <select value={papel} onChange={(e) => trocarPapel(e.target.value as Credencial["papel"])}>
              {PAPEIS.map((p) => (
                <option key={p.valor} value={p.valor}>
                  {p.rotulo}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", margin: "4px 0 12px" }}>
          {PAPEIS.find((p) => p.valor === papel)?.explica}
        </p>

        <fieldset style={{ border: "none", margin: "0 0 12px", padding: 0 }}>
          <legend className="campo" style={{ marginBottom: 6 }}>
            O que esta chave pode fazer{ajustado ? " (ajustado)" : " (padrão do papel)"}
          </legend>
          {ESCOPOS.map((e) => (
            <label key={e.valor} style={{ display: "block", fontSize: 14, marginBottom: 4 }}>
              <input
                type="checkbox"
                checked={escopos.includes(e.valor)}
                onChange={(ev) => alternarEscopo(e.valor, ev.target.checked)}
              />{" "}
              {e.rotulo} <span className="mono" style={{ fontSize: 12 }}>{e.valor}</span>
            </label>
          ))}
        </fieldset>

        <button className="acao primario" disabled={salvando || !nome.trim() || escopos.length === 0}>
          {salvando ? "Emitindo…" : "Emitir chave"}
        </button>
      </form>
    </>
  );
}
