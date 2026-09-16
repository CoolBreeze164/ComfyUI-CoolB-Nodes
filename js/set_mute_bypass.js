import { app } from "../../scripts/app.js"; // Adjust path depth if needed!
import { api } from "../../scripts/api.js";  // Adjust path depth if needed!

app.registerExtension({
    name: "CoolB.SetMuteBypass",
    async setup() {
        // Listen for the event triggered by the Python backend
        api.addEventListener("custom-node-mute-bypass-state", (event) => {
            const nodes = app.graph._nodes_by_id;
            const { node_ids, mode } = event.detail;
            
            // Map UI dropdown to LiteGraph node modes
            let mode_val = 2; // Default to Mute
            if (mode === "Bypass") mode_val = 4;
            else if (mode === "Active") mode_val = 0;

            // Apply the mode to all requested nodes
            if (node_ids && Array.isArray(node_ids)) {
                for (const id of node_ids) {
                    const node = nodes[id];
                    if (node) {
                        node.mode = mode_val;
                    }
                }
            }
        });
    }
});