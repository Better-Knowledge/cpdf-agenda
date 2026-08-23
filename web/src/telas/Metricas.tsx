// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

import { useEffect, useState } from "react";
import { Metricas as Numeros, api, hojeISO, mudarDia } from "../api";
import { ErroAviso } from "../ErroAviso";

// T-10: os números do §4.
//
// A regra que organiza a tela: **sem base de cálculo, nada é mostrado**. Um
// "0% de faltas" num período sem compromisso nenhum não é uma boa notícia —
// é uma frase sem sentido, e é assim que painel engana quem confia nele. A
// API devolve null nesses casos e a tela diz "ainda não dá para dizer".

const ORIGEM_LEGIVEL: Record<string, string> = {
  agente: "conversa",
  cliente: "link público",
  humano: "painel",
  calendly: "Calendly",
};

const PERIODOS = [
  { rotulo: "7 dias", dias: 7 },
  { rotulo: "30 dias", dias: 30 },
  { rotulo: "90 dias", dias: 90 },
];

function Numero({
  rotulo,
  valor,
  sufixo = "%",
  alvo,
}: {
  rotulo: string;
  valor: number | null;
  sufixo?: string;
  alvo?: string;
}) {
  return (
    <div className="numero">
      <span className="rotulo">{rotulo}</span>
      {valor === null ? (
        <span className="sem-base">ainda não dá para dizer</span>
      ) : (
        <span className="grande">
          {valor}
          <small>{sufixo}</small>
        </span>
      )}
      {alvo && <span className="alvo">alvo: {alvo}</span>}
    </div>
  );
}

export function Metricas() {
  const [dias, setDias] = useState(30);
  const [dados, setDados] = useState<Numeros | null>(null);
  const [erro, setErro] = useState<unknown>(null);

  useEffect(() => {
    const ate = hojeISO();
    const de = mudarDia(ate, -dias);
    api
      .get<Numeros>(`/metricas?de=${de}&ate=${ate}`)
      .then(setDados)
      .catch(setErro);
  }, [dias]);

  return (
    <>
      <h1>
        Os <em>números</em>
      </h1>
      <p className="subtitulo">
        Como a agenda andou no período. Cada percentual só aparece quando existe base para
        calculá-lo — período sem compromisso não vira zero.
      </p>
      <ErroAviso erro={erro} />

      <div className="abas" style={{ marginBottom: 20 }}>
        {PERIODOS.map((p) => (
          <button
            key={p.dias}
            type="button"
            className={`aba${p.dias === dias ? " ativa" : ""}`}
            onClick={() => setDias(p.dias)}
          >
            Últimos {p.rotulo}
          </button>
        ))}
      </div>

      {dados && (
        <>
          <div className="cartao" style={{ marginBottom: 20 }}>
            <p style={{ fontSize: 15 }}>{dados.narrativa}</p>
          </div>

          <div className="painel-numeros">
            <Numero rotulo="Agendado por conversa" valor={dados.pct_por_conversa} alvo="≥ 90%" />
            <Numero rotulo="Ocupação da grade" valor={dados.pct_ocupacao} />
            <Numero rotulo="Confirmaram presença" valor={dados.pct_confirmados} />
            <Numero rotulo="Faltas (no que já passou)" valor={dados.pct_no_show} />
            <Numero rotulo="Compromissos no período" valor={dados.total} sufixo="" />
            <Numero rotulo="Esperando na fila" valor={dados.fila_aguardando} sufixo="" />
          </div>

          <div className="cartao" style={{ marginTop: 20 }}>
            <h2 className="bloco">De onde vieram</h2>
            {Object.keys(dados.por_origem).length === 0 ? (
              <div className="vazio">Nenhum agendamento no período.</div>
            ) : (
              <table className="lista">
                <tbody>
                  {Object.entries(dados.por_origem)
                    .sort((a, b) => b[1] - a[1])
                    .map(([origem, quantos]) => (
                      <tr key={origem}>
                        <td>{ORIGEM_LEGIVEL[origem] ?? origem}</td>
                        <td className="mono">{quantos}</td>
                        <td style={{ width: "60%" }}>
                          <div
                            className="barra"
                            style={{ width: `${(100 * quantos) / dados.total}%` }}
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
            <p className="nota-driver">
              A tese do módulo é que a conversa dá conta: o link público e o Calendly existem para
              quem prefere outro caminho, não para substituí-la.
            </p>
          </div>
        </>
      )}
    </>
  );
}
