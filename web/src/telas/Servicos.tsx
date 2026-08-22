import { FormEvent, useCallback, useEffect, useState } from "react";
import { Recurso, Servico, api } from "../api";
import { ErroAviso } from "../ErroAviso";

// T-04: cadastro de serviços. Alterar duração não mexe em agendamentos
// existentes (RF-01) — regra da API, a tela só informa.
export function Servicos() {
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [recursos, setRecursos] = useState<Recurso[]>([]);
  const [erro, setErro] = useState<unknown>(null);
  const [salvando, setSalvando] = useState(false);

  const [nome, setNome] = useState("");
  const [duracao, setDuracao] = useState(60);
  const [preco, setPreco] = useState("0.00");
  const [bufferAntes, setBufferAntes] = useState(0);
  const [bufferDepois, setBufferDepois] = useState(0);
  const [recursosExigidos, setRecursosExigidos] = useState<string[]>([]);

  const carregar = useCallback(async () => {
    setServicos((await api.get<{ items: Servico[] }>("/services?limit=50")).items);
    setRecursos((await api.get<{ items: Recurso[] }>("/resources")).items);
  }, []);

  useEffect(() => {
    carregar().catch(setErro);
  }, [carregar]);

  async function criar(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      await api.post("/services", {
        nome,
        duracao_min: duracao,
        preco,
        buffer_antes_min: bufferAntes,
        buffer_depois_min: bufferDepois,
        resource_ids: recursosExigidos,
      });
      setNome("");
      setRecursosExigidos([]);
      await carregar();
    } catch (e) {
      setErro(e);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <h1>Serviços</h1>
      <p className="subtitulo">
        O que a sua agenda oferece — duração, preço e folga entre atendimentos.
      </p>
      <ErroAviso erro={erro} />

      <div className="cartao" style={{ marginBottom: 20 }}>
        {servicos.length === 0 ? (
          <div className="vazio">Nenhum serviço ainda — cadastre o primeiro abaixo.</div>
        ) : (
          <table className="lista">
            <thead>
              <tr>
                <th>Serviço</th>
                <th>Duração</th>
                <th>Preço</th>
                <th>Folga antes/depois</th>
              </tr>
            </thead>
            <tbody>
              {servicos.map((s) => (
                <tr key={s.id}>
                  <td>
                    <strong>{s.nome}</strong>
                  </td>
                  <td className="mono">{s.duracao_min} min</td>
                  <td className="mono">R$ {s.preco}</td>
                  <td className="mono">
                    {s.buffer_antes_min} / {s.buffer_depois_min} min
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form className="cartao" onSubmit={criar}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>Novo serviço</h2>
        <div className="formulario-linha">
          <label className="campo">
            Nome
            <input value={nome} onChange={(e) => setNome(e.target.value)} required />
          </label>
          <label className="campo">
            Duração (min)
            <input
              type="number"
              min={5}
              step={5}
              value={duracao}
              onChange={(e) => setDuracao(Number(e.target.value))}
            />
          </label>
          <label className="campo">
            Preço (R$)
            <input value={preco} onChange={(e) => setPreco(e.target.value)} placeholder="80.00" />
          </label>
          <label className="campo">
            Folga antes (min)
            <input
              type="number"
              min={0}
              step={5}
              value={bufferAntes}
              onChange={(e) => setBufferAntes(Number(e.target.value))}
            />
          </label>
          <label className="campo">
            Folga depois (min)
            <input
              type="number"
              min={0}
              step={5}
              value={bufferDepois}
              onChange={(e) => setBufferDepois(Number(e.target.value))}
            />
          </label>
        </div>
        {recursos.length > 0 && (
          <fieldset style={{ border: "none", margin: "12px 0" }}>
            <legend className="campo" style={{ marginBottom: 6 }}>
              Exige quais recursos?
            </legend>
            {recursos.map((r) => (
              <label key={r.id} style={{ marginRight: 16, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={recursosExigidos.includes(r.id)}
                  onChange={(e) =>
                    setRecursosExigidos((atual) =>
                      e.target.checked ? [...atual, r.id] : atual.filter((id) => id !== r.id),
                    )
                  }
                />{" "}
                {r.nome}
              </label>
            ))}
          </fieldset>
        )}
        <button className="acao" disabled={salvando || !nome.trim()}>
          {salvando ? "Salvando…" : "Cadastrar serviço"}
        </button>
      </form>
    </>
  );
}
