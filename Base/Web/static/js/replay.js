// Replay Logic

let logData = [];
let isPlaying = false;
let playbackIndex = 0;
let playbackSpeed = 5;
let animationFrameId;

// DOM Elements
const selectLogs = document.getElementById('log-select');
const btnPlay = document.getElementById('btn-play');
const slider = document.getElementById('time-slider');
const timeDisplay = document.getElementById('time-display');
const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');
const selectSpeed = document.getElementById('speed-select');

// Charts
let vChart, cChart;

// Init
window.onload = function () {
    fetchLogs();
    setupCharts();

    // Scale canvas to match table ratio 3000x2000
    // We keep internal resolution 3000x2000
};

selectSpeed.onchange = () => playbackSpeed = parseInt(selectSpeed.value);

slider.oninput = function () {
    playbackIndex = parseInt(this.value);
    updateFrame(playbackIndex);
};

function fetchLogs() {
    fetch('/api/logs/list')
        .then(r => r.json())
        .then(files => {
            selectLogs.innerHTML = '';
            files.forEach(f => {
                let opt = document.createElement('option');
                opt.value = f;
                opt.innerText = f;
                selectLogs.appendChild(opt);
            });
            if (files.length > 0) selectLogs.value = files[0];
        });
}

function loadLog() {
    const filename = selectLogs.value;
    if (!filename) return;

    fetch(`/api/logs/${filename}`)
        .then(r => r.text())
        .then(csvText => {
            parseCSV(csvText);
            resetPlayer();
        });
}

function parseCSV(text) {
    const lines = text.trim().split('\n');
    const headers = lines[0].split(','); // timestamp,match_time,x,y,theta,match_running,fsm_state,voltage,current,cpu_temp

    logData = [];
    for (let i = 1; i < lines.length; i++) {
        const parts = lines[i].split(',');
        if (parts.length < 5) continue;

        let entry = {};
        // Mapping simple based on column order
        entry.t = parseFloat(parts[1]); // match_time
        entry.x = parseFloat(parts[2]);
        entry.y = parseFloat(parts[3]);
        entry.theta = parseFloat(parts[4]);
        entry.running = parts[5];
        entry.state = parts[6];
        entry.volt = parseFloat(parts[7].replace('V', '')); // Clean "12.4V" to 12.4
        entry.curr = parseFloat(parts[8]);

        logData.push(entry);
    }

    console.log(`Loaded ${logData.length} points.`);
    slider.max = logData.length - 1;

    // Update Charts Data
    updateChartsTotal();
}

function resetPlayer() {
    isPlaying = false;
    playbackIndex = 0;
    slider.value = 0;
    btnPlay.innerText = "▶ PLAY";
    updateFrame(0);
}

function togglePlay() {
    if (isPlaying) {
        isPlaying = false;
        btnPlay.innerText = "▶ PLAY";
        cancelAnimationFrame(animationFrameId);
    } else {
        isPlaying = true;
        btnPlay.innerText = "⏸ PAUSE";
        lastLoopTime = Date.now();
        loop();
    }
}

let lastLoopTime = 0;
function loop() {
    if (!isPlaying) return;

    const now = Date.now();
    const dt = (now - lastLoopTime) / 1000;
    lastLoopTime = now;

    // Advance frames based on speed (assuming 10Hz log = 0.1s per frame)
    // Speed x1 = 10 frames per second
    const framesToAdvance = (dt * 10) * playbackSpeed;

    if (framesToAdvance >= 1) {
        playbackIndex += Math.round(framesToAdvance);
        if (playbackIndex >= logData.length) {
            playbackIndex = logData.length - 1;
            isPlaying = false;
            btnPlay.innerText = "▶ PLAY";
        }
        slider.value = playbackIndex;
        updateFrame(playbackIndex);
    }

    animationFrameId = requestAnimationFrame(loop);
}

function updateFrame(idx) {
    if (!logData[idx]) return;
    const d = logData[idx];

    // Text
    timeDisplay.innerText = d.t.toFixed(2) + "s";
    document.getElementById('val-batt').innerText = d.volt + " V";
    document.getElementById('val-curr').innerText = d.curr + " A";
    document.getElementById('val-state').innerText = d.state;

    // Map
    drawMap(d);

    // Charts Cursor (optional optimization: only update dataset point radius?)
    // For now simple
}

function drawMap(currentData) {
    // Clear
    ctx.fillStyle = "#222";
    ctx.fillRect(0, 0, 3000, 2000);

    // Draw Base Table (Green 3000x2000)
    ctx.fillStyle = "#0055aa"; // Blue team side color for example
    ctx.fillRect(0, 0, 3000, 2000);

    // Draw Path
    ctx.beginPath();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.5)";
    ctx.lineWidth = 5;
    if (logData.length > 0) ctx.moveTo(logData[0].x, 2000 - logData[0].y); // Invert Y for canvas

    for (let i = 0; i < playbackIndex; i += 5) { // Optimization: skip points
        let p = logData[i];
        ctx.lineTo(p.x, 2000 - p.y);
    }
    ctx.stroke();

    // Draw Robot
    const rx = currentData.x;
    const ry = 2000 - currentData.y;
    const size = 300; // Robot size roughly

    ctx.save();
    ctx.translate(rx, ry);
    ctx.rotate(-currentData.theta * Math.PI / 180); // Invert angle for canvas?

    ctx.fillStyle = "yellow";
    ctx.fillRect(-size / 2, -size / 2, size, size);

    // Direction Line
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(size / 2 + 50, 0);
    ctx.strokeStyle = "red";
    ctx.lineWidth = 10;
    ctx.stroke();

    ctx.restore();
}

function setupCharts() {
    vChart = new Chart(document.getElementById('chart-voltage'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Voltage (V)', data: [], borderColor: '#4CAF50', pointRadius: 0 }] },
        options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });

    cChart = new Chart(document.getElementById('chart-current'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Current (A)', data: [], borderColor: '#FF9800', pointRadius: 0 }] },
        options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });
}

function updateChartsTotal() {
    const labels = logData.map((d, i) => i);
    const volts = logData.map(d => d.volt);
    const currs = logData.map(d => d.curr);

    vChart.data.labels = labels;
    vChart.data.datasets[0].data = volts;
    vChart.update();

    cChart.data.labels = labels;
    cChart.data.datasets[0].data = currs;
    cChart.update();
}
