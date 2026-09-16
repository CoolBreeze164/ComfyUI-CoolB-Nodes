import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "CoolB.Textbox", 

    beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "CBTextbox") {
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);

                for (const widget of this.widgets) {
                    // 'customtext' is the widget type for multiline text in ComfyUI
                    if (widget.type === "customtext" || widget.type === "text") {
                        // Overwrite the widget with the stringified input
                        // Note: This requires the Python node to return {"text": [string]} 
                        // because .join("") is an Array method.
                        widget.value = message.text.join("");
                    }
                }
                this.onResize?.(this.size);
            };
        }
    },
});