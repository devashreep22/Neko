import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import PetApp from "./PetApp.jsx";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("NekoAI mount element #root was not found");

const isPetWindow = new URLSearchParams(window.location.search).get("pet") === "1";
if (isPetWindow) document.body.classList.add("pet-window");

createRoot(rootElement).render(
  <React.StrictMode>
    {isPetWindow ? <PetApp /> : <App />}
  </React.StrictMode>,
);
