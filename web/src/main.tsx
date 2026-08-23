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
import { Canal } from "./telas/Canal";
import { Dia } from "./telas/Dia";
import { Entrar } from "./telas/Entrar";
import { Grade } from "./telas/Grade";
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
          <Route path="/canal" element={<Canal />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
