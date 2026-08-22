import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { portalTheme } from "./theme/tokens";
import "./theme/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={portalTheme}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ConfigProvider>
  </StrictMode>,
);
