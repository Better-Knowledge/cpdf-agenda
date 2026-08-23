import { createContext, useCallback, useContext, useRef, useState } from "react";

// O toast é o retorno padrão de toda ação bem-sucedida (DS §3.10).
// Pílula tinta sobre a base; some sozinha em ~3s.

type Avisar = (mensagem: string, tipo?: "ok" | "erro") => void;

const ToastContexto = createContext<Avisar>(() => {});

export const usarToast = () => useContext(ToastContexto);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [atual, setAtual] = useState<{ mensagem: string; tipo: "ok" | "erro" } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const avisar = useCallback<Avisar>((mensagem, tipo = "ok") => {
    clearTimeout(timer.current);
    setAtual({ mensagem, tipo });
    timer.current = setTimeout(() => setAtual(null), 3000);
  }, []);

  return (
    <ToastContexto.Provider value={avisar}>
      {children}
      {atual && (
        <div className={`toast${atual.tipo === "erro" ? " erro" : ""}`} role="status">
          {atual.mensagem}
        </div>
      )}
    </ToastContexto.Provider>
  );
}
