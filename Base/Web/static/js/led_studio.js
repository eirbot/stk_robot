document.addEventListener("DOMContentLoaded", () => {
    // CONSTANTS
    const LED_COUNT = 288;
    const API_URL = "/api/led_animations";

    // STATE
    let animations = {};
    let currentAnimName = null;
    let currentSequence = { steps: [] }; // { steps: [ {duration, transition, pixels: []} ] }
    let currentStepIndex = -1;
    let isDrawing = false;
    let currentTool = 'pen'; // pen, fill, eraser

    // DOM ELEMENTS
    const ledMatrix = document.getElementById("ledMatrix");
    const stepList = document.getElementById("stepList");
    const colorPicker = document.getElementById("colorPicker");
    const stepDuration = document.getElementById("stepDuration");
    const stepTransition = document.getElementById("stepTransition");
    const animSelect = document.getElementById("animSelect");
    const modal = document.getElementById("saveModal");
    const animNameInput = document.getElementById("animNameInput");

    const chkLoop = document.getElementById("chkLoop");

    // --- INITIALIZATION ---
    initMatrix();
    loadAnimations();

    // --- MATRIX LOGIC ---
    function initMatrix() {
        ledMatrix.innerHTML = "";
        for (let i = 0; i < LED_COUNT; i++) {
            const led = document.createElement("div");
            led.className = "led";
            led.dataset.index = i;
            led.style.backgroundColor = "#000000";

            led.addEventListener("mousedown", (e) => {
                isDrawing = true;
                applyTool(i);
            });
            led.addEventListener("mouseenter", (e) => {
                if (isDrawing) applyTool(i);
            });

            ledMatrix.appendChild(led);
        }
    }

    document.addEventListener("mouseup", () => isDrawing = false);

    function applyTool(index) {
        if (currentStepIndex === -1) return; // No step selected

        const leds = document.querySelectorAll(".led");
        const color = currentTool === 'eraser' ? '#000000' : colorPicker.value;

        if (currentTool === 'fill') {
            currentSequence.steps[currentStepIndex].pixels = new Array(LED_COUNT).fill(hexToRgb(color));
            renderMatrixFromStep(currentSequence.steps[currentStepIndex]);
        } else {
            // Update Data
            // Ensure array is initialized
            if (!currentSequence.steps[currentStepIndex].pixels) {
                currentSequence.steps[currentStepIndex].pixels = new Array(LED_COUNT).fill([0, 0, 0]);
            }
            currentSequence.steps[currentStepIndex].pixels[index] = hexToRgb(color);

            // Update UI
            leds[index].style.backgroundColor = color;
        }
        updateStepPreview(currentStepIndex);
    }

    function hexToRgb(hex) {
        const r = parseInt(hex.substring(1, 3), 16);
        const g = parseInt(hex.substring(3, 5), 16);
        const b = parseInt(hex.substring(5, 7), 16);
        return [r, g, b];
    }

    function rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }

    // --- SEQUENCER LOGIC ---
    function renderStepList() {
        stepList.innerHTML = "";
        currentSequence.steps.forEach((step, index) => {
            const item = document.createElement("div");
            item.className = `step-item ${index === currentStepIndex ? 'active' : ''}`;

            // Reorder buttons logic
            const isFirst = index === 0;
            const isLast = index === currentSequence.steps.length - 1;

            item.innerHTML = `
                <div class="step-info">
                    <strong>Étape ${index + 1}</strong><br>
                    <small>${step.duration}s - ${step.transition}</small>
                </div>
                <div class="step-actions">
                    <div class="move-btns">
                        <button onclick="moveStep(${index}, -1)" ${isFirst ? 'disabled style="opacity:0.3"' : ''}>⬆</button>
                        <button onclick="moveStep(${index}, 1)" ${isLast ? 'disabled style="opacity:0.3"' : ''}>⬇</button>
                    </div>
                    <button onclick="copyStep(${index})">📋</button>
                    <button onclick="deleteStep(${index})">❌</button>
                </div>
            `;
            item.addEventListener("click", (e) => {
                if (!e.target.closest("button")) selectStep(index);
            });
            stepList.appendChild(item);
        });

        // Update Loop Checkbox state
        chkLoop.checked = currentSequence.loop || false;
    }

    // Checkbox listener
    chkLoop.addEventListener("change", () => {
        currentSequence.loop = chkLoop.checked;
    });

    function selectStep(index) {
        currentStepIndex = index;
        renderStepList();

        const step = currentSequence.steps[index];
        stepDuration.value = step.duration;
        stepTransition.value = step.transition;

        renderMatrixFromStep(step);
    }

    function renderMatrixFromStep(step) {
        const leds = document.querySelectorAll(".led");
        const pixels = step.pixels || [];

        for (let i = 0; i < LED_COUNT; i++) {
            const c = pixels[i] || [0, 0, 0];
            leds[i].style.backgroundColor = rgbToHex(c[0], c[1], c[2]);
        }
    }

    function updateStepDataFromInputs() {
        if (currentStepIndex === -1) return;
        currentSequence.steps[currentStepIndex].duration = parseFloat(stepDuration.value);
        currentSequence.steps[currentStepIndex].transition = stepTransition.value;
        renderStepList();
    }

    document.getElementById("btnAddStep").addEventListener("click", () => {
        let newPixels = new Array(LED_COUNT).fill([0, 0, 0]);
        // Copy previous if exists
        if (currentSequence.steps.length > 0) {
            const prev = currentSequence.steps[currentSequence.steps.length - 1];
            newPixels = JSON.parse(JSON.stringify(prev.pixels));
        }

        currentSequence.steps.push({
            duration: 1.0,
            transition: "NONE",
            pixels: newPixels
        });
        selectStep(currentSequence.steps.length - 1);
    });

    window.deleteStep = (index) => {
        if (confirm("Supprimer l'étape ?")) {
            currentSequence.steps.splice(index, 1);
            if (currentSequence.steps.length === 0) currentStepIndex = -1;
            else selectStep(Math.max(0, index - 1));
            renderStepList();
        }
    };

    window.copyStep = (index) => {
        const step = currentSequence.steps[index];
        const newStep = JSON.parse(JSON.stringify(step));
        currentSequence.steps.splice(index + 1, 0, newStep);
        selectStep(index + 1);
    };

    window.moveStep = (index, direction) => {
        // direction: -1 (up) or 1 (down)
        if (direction === -1 && index > 0) {
            const temp = currentSequence.steps[index];
            currentSequence.steps[index] = currentSequence.steps[index - 1];
            currentSequence.steps[index - 1] = temp;
            selectStep(index - 1);
        } else if (direction === 1 && index < currentSequence.steps.length - 1) {
            const temp = currentSequence.steps[index];
            currentSequence.steps[index] = currentSequence.steps[index + 1];
            currentSequence.steps[index + 1] = temp;
            selectStep(index + 1);
        }
    };

    stepDuration.addEventListener("change", updateStepDataFromInputs);
    stepTransition.addEventListener("change", updateStepDataFromInputs);

    // --- TOOLS ---
    document.querySelectorAll(".tool-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tool-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentTool = btn.dataset.tool;
        });
    });

    // --- API & IO ---
    async function loadAnimations() {
        try {
            const res = await fetch(API_URL);
            animations = await res.json();
            updateAnimSelect();
        } catch (e) { console.error(e); }
    }

    function updateAnimSelect() {
        animSelect.innerHTML = '<option value="">-- Nouvelle Animation --</option>';
        Object.keys(animations).forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            animSelect.appendChild(opt);
        });
        if (currentAnimName) animSelect.value = currentAnimName;
    }

    animSelect.addEventListener("change", () => {
        if (!animSelect.value) {
            // New
            currentAnimName = null;
            currentSequence = { steps: [], loop: false };
            currentStepIndex = -1;
            renderStepList();
            initMatrix(); // Clear visual
            chkLoop.checked = false;
        } else {
            // Load
            currentAnimName = animSelect.value;
            currentSequence = JSON.parse(JSON.stringify(animations[currentAnimName]));
            if (typeof currentSequence.loop === 'undefined') currentSequence.loop = false;

            chkLoop.checked = currentSequence.loop;

            if (currentSequence.steps.length > 0) selectStep(0);
            else renderStepList();
        }
    });

    document.getElementById("btnNew").addEventListener("click", () => {
        animSelect.value = "";
        animSelect.dispatchEvent(new Event("change"));
    });

    document.getElementById("btnSave").addEventListener("click", () => {
        if (!currentSequence.steps.length) return alert("Ajoutez au moins une étape !");

        animNameInput.value = currentAnimName || "";
        modal.classList.add("show");
    });

    document.getElementById("btnConfirmSave").addEventListener("click", async () => {
        const name = animNameInput.value.trim();
        if (!name) return alert("Nom invalide");

        animations[name] = currentSequence;
        currentAnimName = name; // Update current

        try {
            await fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(animations)
            });
            modal.classList.remove("show");
            updateAnimSelect();
            alert("Sauvegardé !");
        } catch (e) { alert("Erreur sauvegarde"); }
    });

    document.getElementById("btnCancelSave").addEventListener("click", () => modal.classList.remove("show"));

    document.getElementById("btnDelete").addEventListener("click", async () => {
        if (!currentAnimName) return;
        if (!confirm(`Supprimer ${currentAnimName} ?`)) return;

        delete animations[currentAnimName];
        await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(animations)
        });
        currentAnimName = null;
        updateAnimSelect();
        animSelect.value = "";
        animSelect.dispatchEvent(new Event("change"));
    });

    document.getElementById("btnPlay").addEventListener("click", () => {
        if (!currentAnimName) return alert("Sauvegardez d'abord l'animation !");
        fetch("/api/play_animation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: currentAnimName })
        });
    });

    document.getElementById("btnStop").addEventListener("click", () => {
        // Send OFF logic if implemented, or just Black
        // For now maybe we don't have a STOP api, let's assume OFF command
        // But verifying routes.py, we have OFF in led_control.
        fetch("/api/led_control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "color", value: "0,0,0" })
        });
    });

    function updateStepPreview(index) {
        // Only update Matrix view if it is the currently selected step
        // (Already handled by draw logic)
    }
});
