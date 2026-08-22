import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bloqueio, Recurso, Regra, api } from "../api";
import { ErroAviso } from "../ErroAviso";

// T-05: horário de trabalho semanal por recurso + bloqueios pontuais.
const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

const hora = (t: string) => t.slice(0, 5);
const dataHoraLocal = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

export function Grade() {
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [recursoAtivo, setRecursoAtivo] = useState<string>("");
  const [regras, setRegras] = useState<Regra[]>([]);
  const [bloqueios, setBloqueios] = useState<Bloqueio[]>([]);
  const [erro, setErro] = useState<unknown>(null);

  const [novoRecurso, setNovoRecurso] = useState("");
  const [dia, setDia] = useState(0);
  const [inicio, setInicio] = useState("09:00");
  const [fim, setFim] = useState("18:00");
  const [bloqueioInicio, setBloqueioInicio] = useState("");
  const [bloqueioFim, setBloqueioFim] = useState("");
  const [motivo, setMotivo] = useState("");

  const carregar = useCallback(async () => {
    const lista = (await api.get<{ items: Recurso[] }>("/resources")).items;
    setRecursos(lista);
    setRecursoAtivo((atual) => atual || lista[0]?.id || "");
    setRegras(await api.get<Regra[]>("/availability/rules"));
  }, []);

  useEffect(() => {
    carregar().catch(setErro);
  }, [carregar]);

  useEffect(() => {
    if (!recursoAtivo) return;
    api
      .get<Bloqueio[]>(`/availability/blocks?resource_id=${recursoAtivo}`)
      .then(setBloqueios)
      .catch(setErro);
  }, [recursoAtivo]);

  async function agir(acao: () => Promise<unknown>) {
    setErro(null);
    try {
      await acao();
      await carregar();
      if (recursoAtivo)
        setBloqueios(await api.get<Bloqueio[]>(`/availability/blocks?resource_id=${recursoAtivo}`));
    } catch (e) {
      setErro(e);
    }
  }

  function criarRecurso(evento: FormEvent) {
    evento.preventDefault();
    agir(() => api.post("/resources", { nome: novoRecurso })).then(() => setNovoRecurso(""));
  }

  const regrasDoRecurso = regras.filter((r) => r.resource_id === recursoAtivo);

  return (
    <>
      <h1>Grade e bloqueios</h1>
      <p className="subtitulo">
        O motor de horários só oferece o que estiver dentro da grade — e fora dos bloqueios.
      </p>
      <ErroAviso erro={erro} />

      <div className="cartao" style={{ marginBottom: 20 }}>
        <form className="formulario-linha" onSubmit={criarRecurso}>
          <label className="campo">
            Novo recurso (profissional, sala, equipamento)
            <input
              value={novoRecurso}
              onChange={(e) => setNovoRecurso(e.target.value)}
              placeholder="ex.: Dra. Ana"
            />
          </label>
          <button className="acao secundaria" disabled={!novoRecurso.trim()}>
            Adicionar recurso
          </button>
        </form>
      </div>

      {recursos.length > 0 && (
        <>
          <label className="campo" style={{ maxWidth: 320 }}>
            Recurso
            <select value={recursoAtivo} onChange={(e) => setRecursoAtivo(e.target.value)}>
              {recursos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nome}
                </option>
              ))}
            </select>
          </label>

          <div className="cartao" style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>Horário de trabalho</h2>
            {regrasDoRecurso.length === 0 ? (
              <div className="vazio">
                Sem grade ainda — sem horário de trabalho, nenhum slot é oferecido.
              </div>
            ) : (
              <table className="lista">
                <thead>
                  <tr>
                    <th>Dia</th>
                    <th>Das</th>
                    <th>Às</th>
                  </tr>
                </thead>
                <tbody>
                  {regrasDoRecurso
                    .slice()
                    .sort((a, b) => a.dia_semana - b.dia_semana)
                    .map((r) => (
                      <tr key={r.id}>
                        <td>{DIAS[r.dia_semana]}</td>
                        <td className="mono">{hora(r.hora_inicio)}</td>
                        <td className="mono">{hora(r.hora_fim)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
            <form
              className="formulario-linha"
              style={{ marginTop: 14 }}
              onSubmit={(e) => {
                e.preventDefault();
                agir(() =>
                  api.post("/availability/rules", {
                    resource_id: recursoAtivo,
                    dia_semana: dia,
                    hora_inicio: inicio,
                    hora_fim: fim,
                  }),
                );
              }}
            >
              <label className="campo">
                Dia da semana
                <select value={dia} onChange={(e) => setDia(Number(e.target.value))}>
                  {DIAS.map((nome, i) => (
                    <option key={i} value={i}>
                      {nome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="campo">
                Das
                <input type="time" value={inicio} onChange={(e) => setInicio(e.target.value)} />
              </label>
              <label className="campo">
                Às
                <input type="time" value={fim} onChange={(e) => setFim(e.target.value)} />
              </label>
              <button className="acao">Adicionar janela</button>
            </form>
          </div>

          <div className="cartao">
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>Bloqueios pontuais</h2>
            {bloqueios.length === 0 ? (
              <div className="vazio">Nenhum bloqueio futuro — férias e feriados entram aqui.</div>
            ) : (
              <table className="lista">
                <thead>
                  <tr>
                    <th>De</th>
                    <th>Até</th>
                    <th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {bloqueios.map((b) => (
                    <tr key={b.id}>
                      <td className="mono">{dataHoraLocal(b.inicio)}</td>
                      <td className="mono">{dataHoraLocal(b.fim)}</td>
                      <td>{b.motivo ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <form
              className="formulario-linha"
              style={{ marginTop: 14 }}
              onSubmit={(e) => {
                e.preventDefault();
                agir(() =>
                  api.post("/availability/blocks", {
                    resource_id: recursoAtivo,
                    inicio: `${bloqueioInicio}:00-03:00`,
                    fim: `${bloqueioFim}:00-03:00`,
                    motivo: motivo || null,
                  }),
                ).then(() => {
                  setBloqueioInicio("");
                  setBloqueioFim("");
                  setMotivo("");
                });
              }}
            >
              <label className="campo">
                De
                <input
                  type="datetime-local"
                  value={bloqueioInicio}
                  onChange={(e) => setBloqueioInicio(e.target.value)}
                  required
                />
              </label>
              <label className="campo">
                Até
                <input
                  type="datetime-local"
                  value={bloqueioFim}
                  onChange={(e) => setBloqueioFim(e.target.value)}
                  required
                />
              </label>
              <label className="campo">
                Motivo
                <input
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  placeholder="ex.: férias"
                />
              </label>
              <button className="acao">Bloquear período</button>
            </form>
          </div>
        </>
      )}
    </>
  );
}
