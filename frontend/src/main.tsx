import { createRoot } from "react-dom/client";
import InsightDashboard from "./components/insight-dashboard";
import "./styles/base.css";

const mount = document.getElementById("root");
if (!mount) throw new Error("Application root is missing");
createRoot(mount).render(<InsightDashboard />);
