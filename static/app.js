// --- State ---
let state = {
    sessionId: null,
    handId: null,
    handNumber: 0,
    selectedSeat: 0,
    selectedStreet: "preflop",
    selectedPosition: null,
    numSeats: 6,
    stats: {},  // seat -> stat object
};

let ws = null;

// --- API helpers ---
async function api(method, path, body = null) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`/api${path}`, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `API error ${res.status}`);
    }
    return res.json();
}

// --- WebSocket ---
function connectWS() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/hud`);

    ws.onopen = () => {
        document.getElementById("connectionStatus").textContent = "Connected";
        document.getElementById("connectionStatus").className = "connection-status connected";
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "stats_update") {
            state.stats = {};
            for (const s of msg.data) {
                state.stats[s.seat] = s;
            }
            renderHUD();
        }
    };

    ws.onclose = () => {
        document.getElementById("connectionStatus").textContent = "Disconnected";
        document.getElementById("connectionStatus").className = "connection-status disconnected";
        // Reconnect after 2 seconds
        setTimeout(connectWS, 2000);
    };
}

// --- Render HUD ---
function getVpipClass(vpip) {
    if (vpip === null || vpip === undefined) return "";
    if (vpip < 20) return "vpip-tight";
    if (vpip < 30) return "vpip-normal";
    if (vpip < 45) return "vpip-loose";
    return "vpip-very-loose";
}

function renderHUD() {
    const table = document.getElementById("pokerTable");
    table.innerHTML = "";

    for (let i = 0; i < state.numSeats; i++) {
        const seat = document.createElement("div");
        seat.className = `seat seat-${i}`;

        const s = state.stats[i];

        if (s && s.hands_played > 0) {
            const vpipClass = getVpipClass(s.vpip);
            seat.innerHTML = `
                <div class="player-label">Seat ${i + 1}</div>
                <div class="stat-box">
                    <div class="stat-line">
                        <span class="stat-label">VPIP</span>
                        <span class="stat-value ${vpipClass}">${s.vpip !== null ? s.vpip + "%" : "-"}</span>
                    </div>
                    <div class="stat-line">
                        <span class="stat-label">PFR</span>
                        <span class="stat-value">${s.pfr !== null ? s.pfr + "%" : "-"}</span>
                    </div>
                    <div class="stat-line">
                        <span class="stat-label">3Bet</span>
                        <span class="stat-value">${s.three_bet_pct !== null ? s.three_bet_pct + "%" : "-"}</span>
                    </div>
                    <div class="stat-line">
                        <span class="stat-label">AF</span>
                        <span class="stat-value">${s.aggression_factor !== null ? s.aggression_factor : "-"}</span>
                    </div>
                    <div class="sample-size">${s.hands_played} hands</div>
                </div>
            `;
        } else {
            seat.innerHTML = `
                <div class="player-label">Seat ${i + 1}</div>
                <div class="stat-box">
                    <div style="color: #555; font-size: 10px;">No data</div>
                </div>
            `;
        }

        table.appendChild(seat);
    }
}

function renderSeatSelector() {
    const container = document.getElementById("seatSelector");
    container.innerHTML = "";
    for (let i = 0; i < state.numSeats; i++) {
        const btn = document.createElement("button");
        btn.textContent = `Seat ${i + 1}`;
        btn.dataset.seat = i;
        if (i === state.selectedSeat) btn.className = "active";
        btn.addEventListener("click", () => {
            state.selectedSeat = i;
            renderSeatSelector();
        });
        container.appendChild(btn);
    }
}

function updateHandInfo() {
    const el = document.getElementById("handInfo");
    if (!state.sessionId) {
        el.textContent = "No active session";
    } else if (!state.handId) {
        el.textContent = `Session #${state.sessionId} — Click "New Hand" to start`;
    } else {
        el.textContent = `Session #${state.sessionId} — Hand #${state.handNumber} — ${state.selectedStreet}`;
    }
}

function addLogEntry(text) {
    const log = document.getElementById("actionLog");
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.textContent = text;
    log.prepend(entry);
    // Keep log size manageable
    while (log.children.length > 100) {
        log.removeChild(log.lastChild);
    }
}

// --- Refresh stats from API ---
async function refreshStats() {
    if (!state.sessionId) return;
    try {
        const stats = await api("GET", `/sessions/${state.sessionId}/stats`);
        state.stats = {};
        for (const s of stats) {
            state.stats[s.seat] = s;
        }
        renderHUD();
    } catch (e) {
        console.error("Failed to refresh stats:", e);
    }
}

// --- Event handlers ---

document.getElementById("startSession").addEventListener("click", async () => {
    const gameType = document.getElementById("gameType").value;
    const stakes = document.getElementById("stakes").value || null;

    try {
        const session = await api("POST", "/sessions", { game_type: gameType, stakes });
        state.sessionId = session.id;
        state.handId = null;
        state.handNumber = 0;

        // Update seat count based on game type
        state.numSeats = gameType.includes("9max") ? 9 : 6;
        renderSeatSelector();
        renderHUD();
        updateHandInfo();

        document.getElementById("startSession").style.display = "none";
        document.getElementById("endSession").style.display = "";

        addLogEntry(`Session #${session.id} started (${gameType})`);
    } catch (e) {
        alert("Failed to start session: " + e.message);
    }
});

document.getElementById("endSession").addEventListener("click", async () => {
    if (!state.sessionId) return;
    try {
        await api("POST", `/sessions/${state.sessionId}/end`);
        addLogEntry(`Session #${state.sessionId} ended`);
        state.sessionId = null;
        state.handId = null;
        state.handNumber = 0;
        updateHandInfo();

        document.getElementById("startSession").style.display = "";
        document.getElementById("endSession").style.display = "none";
    } catch (e) {
        alert("Failed to end session: " + e.message);
    }
});

document.getElementById("newHand").addEventListener("click", async () => {
    if (!state.sessionId) {
        alert("Start a session first");
        return;
    }
    try {
        const hand = await api("POST", `/sessions/${state.sessionId}/hands`);
        state.handId = hand.id;
        state.handNumber = hand.hand_number;
        state.selectedStreet = "preflop";

        // Reset street selector
        document.querySelectorAll("#streetSelector button").forEach(b => b.classList.remove("active"));
        document.querySelector('#streetSelector button[data-street="preflop"]').classList.add("active");

        updateHandInfo();
        addLogEntry(`--- Hand #${hand.hand_number} ---`);
    } catch (e) {
        alert("Failed to start hand: " + e.message);
    }
});

// Street selector
document.querySelectorAll("#streetSelector button").forEach(btn => {
    btn.addEventListener("click", () => {
        state.selectedStreet = btn.dataset.street;
        document.querySelectorAll("#streetSelector button").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        updateHandInfo();
    });
});

// Position selector
document.querySelectorAll("#positionSelector button").forEach(btn => {
    btn.addEventListener("click", () => {
        if (state.selectedPosition === btn.dataset.pos) {
            state.selectedPosition = null;
            btn.classList.remove("active");
        } else {
            state.selectedPosition = btn.dataset.pos;
            document.querySelectorAll("#positionSelector button").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
        }
    });
});

// Action buttons
document.querySelectorAll(".action-buttons button").forEach(btn => {
    btn.addEventListener("click", async () => {
        if (!state.handId) {
            alert("Start a new hand first");
            return;
        }

        const action = btn.dataset.action;
        const amount = document.getElementById("betAmount").value
            ? parseFloat(document.getElementById("betAmount").value)
            : null;

        // Determine if this is a voluntary action (not a blind post)
        const isVoluntary = !(
            state.selectedStreet === "preflop" &&
            (state.selectedPosition === "SB" || state.selectedPosition === "BB") &&
            action === "call" &&
            amount === null
        );

        try {
            await api("POST", `/hands/${state.handId}/actions`, {
                seat: state.selectedSeat,
                street: state.selectedStreet,
                action: action,
                amount: amount,
                is_voluntary: isVoluntary,
                position: state.selectedPosition,
            });

            const amountStr = amount ? ` $${amount}` : "";
            addLogEntry(`Seat ${state.selectedSeat + 1} (${state.selectedPosition || "?"}) ${action}${amountStr} [${state.selectedStreet}]`);

            // Clear amount
            document.getElementById("betAmount").value = "";

            // Refresh stats
            await refreshStats();
        } catch (e) {
            alert("Failed to log action: " + e.message);
        }
    });
});

// Game type change updates seat count
document.getElementById("gameType").addEventListener("change", (e) => {
    state.numSeats = e.target.value.includes("9max") ? 9 : 6;
    renderSeatSelector();
    renderHUD();
});

// --- Init ---
renderSeatSelector();
renderHUD();
updateHandInfo();
connectWS();
