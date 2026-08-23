import "@fontsource/fira-sans/500.css";
import "@fontsource/fira-sans/600.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/libre-baskerville/400-italic.css";
import "@fontsource/libre-baskerville/400.css";
import "@fontsource/libre-baskerville/700.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./Layout";
import { sessao } from "./api";
import "./estilos.css";
import { Agendar } from "./telas/Agendar";
import { Calendarios } from "./telas/Calendarios";
import { Canal } from "./telas/Canal";
import { Credenciais } from "./telas/Credenciais";
import { Dia } from "./telas/Dia";
import { Fila } from "./telas/Fila";
import { Entrar } from "./telas/Entrar";
import { Grade } from "./telas/Grade";
import { Links } from "./telas/Links";
import { Servicos } from "./telas/Servicos";

function Protegido({ children }: { children: React.ReactNode }) {
  if (!sessao.chave()) return <Navigate to="/entrar" replace />;
  return <>{children}</>;
}

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter basename="/app">
      <Routes>
        <Route path="/entrar" element={<Entrar />} />
        {/* P-01: pública de propósito — fora do Protegido, sem credencial. */}
        <Route path="/agendar/:slug" element={<Agendar />} />
        <Route
          element={
            <Protegido>
              <Layout />
            </Protegido>
          }
        >
          <Route path="/" element={<Navigate to="/dia" replace />} />
          <Route path="/dia" element={<Dia />} />
          <Route path="/servicos" element={<Servicos />} />
          <Route path="/grade" element={<Grade />} />
          <Route path="/fila" element={<Fila />} />
          <Route path="/links" element={<Links />} />
          <Route path="/calendarios" element={<Calendarios />} />
          <Route path="/canal" element={<Canal />} />
          <Route path="/credenciais" element={<Credenciais />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
