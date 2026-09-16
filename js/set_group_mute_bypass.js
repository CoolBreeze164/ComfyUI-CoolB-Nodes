import { app } from "../../scripts/app.js"; // Adjust path depth if needed!
import { api } from "../../scripts/api.js";  // Adjust path depth if needed!

/**
 * Helper to determine if a node is physically inside a group.
 * Based on rgthree's logic: checks if the node's center point is inside the group's bounding box.
 */
function isNodeInGroup(node, group) {
    // Get node bounding box [x, y, w, h]
    let bounds;
    if (typeof node.getBounding === 'function') {
        bounds = node.getBounding();
    } else if (node.pos && node.size) {
        bounds = [node.pos[0], node.pos[1], node.size[0], node.size[1]];
    } else {
        return false;
    }
    
    // Calculate the center of the node
    const center = [bounds[0] + bounds[2] * 0.5, bounds[1] + bounds[3] * 0.5];
    
    // Get group bounding box (handles different LiteGraph versions)
    const gb = group.bounding || group._bounding;
    if (!gb) return false;
    
    // Check if node center is inside the group's bounding box
    return center[0] >= gb[0] &&
           center[0] < gb[0] + gb[2] &&
           center[1] >= gb[1] &&
           center[1] < gb[1] + gb[3];
}

app.registerExtension({
    name: "CoolB.SetGroupMuteBypass",
    async setup() {
        api.addEventListener("custom-group-mute-bypass-state", (event) => {
            const { search_str, mode } = event.detail;
            
            // Prevent muting ALL groups if the input is empty
            if (!search_str || search_str.trim() === "") return;
            
            let mode_val = 2; // Default to Mute
            if (mode === "Bypass") mode_val = 4;
            else if (mode === "Active") mode_val = 0;

            const graph = app.graph;
            const groups = graph._groups || [];
            const nodes_by_id = graph._nodes_by_id;

            for (const group of groups) {
                const title = group.title || "";
                
                // Substring match (case-insensitive for better UX)
                if (title.toLowerCase().includes(search_str.toLowerCase())) {
                    for (const id in nodes_by_id) {
                        const node = nodes_by_id[id];
                        if (isNodeInGroup(node, group)) {
                            node.mode = mode_val;
                        }
                    }
                }
            }
        });
    }
});