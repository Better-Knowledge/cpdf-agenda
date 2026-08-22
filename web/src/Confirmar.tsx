import { useEffect, useState } from "react";

/** Ação destrutiva pede confirmação (§12.3): o primeiro clique arma o botão,
 *  o segundo executa. Desarma sozinho depois de alguns segundos. */
export function BotaoConfirmar({
  rotulo,
  confirmacao = "Tem certeza?",
  onConfirmar,
  desabilitado = false,
  miudo = false,
}: {
  rotulo: string;
  confirmacao?: string;
  onConfirmar: () => void;
  desabilitado?: boolean;
  miudo?: boolean;
}) {
  const [armado, setArmado] = useState(false);

  useEffect(() => {
    if (!armado) return;
    const timer = setTimeout(() => setArmado(false), 4000);
    return () => clearTimeout(timer);
  }, [armado]);

  return (
    <button
      type="button"
      className={`acao perigosa${armado ? " armado" : ""}${miudo ? " miuda" : ""}`}
      disabled={desabilitado}
      onClick={() => {
        if (armado) {
          setArmado(false);
          onConfirmar();
        } else {
          setArmado(true);
        }
      }}
    >
      {armado ? confirmacao : rotulo}
    </button>
  );
}
