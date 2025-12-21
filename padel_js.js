// =================================================================================================
// DEBUG MODE - VISUAL INDICATOR (SET TO false IN PRODUCTION)
// =================================================================================================
const DEBUG_MODE = true;

if (DEBUG_MODE) {
    const debugDiv = document.createElement('div');
    debugDiv.id = 'debugOverlay';
    debugDiv.style.cssText = `
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(0,0,0,0.95);
        color: lime;
        padding: 15px;
        font-family: monospace;
        font-size: 13px;
        z-index: 99999;
        border: 2px solid lime;
        border-radius: 8px;
        min-width: 280px;
        box-shadow: 0 0 20px rgba(0,255,0,0.3);
    `;
    window.addEventListener('load', () => {
        document.body.appendChild(debugDiv);
        setInterval(updateDebugDisplay, 100);
    });
}

function updateDebugDisplay() {
    if (!DEBUG_MODE) return;
    const debugDiv = document.getElementById('debugOverlay');
    if (!debugDiv) return;
    
    const splashActive = DOM.splashScreen?.classList.contains('active') || false;
    const modeVisible = DOM.modeSelectionScreen?.style.display === 'flex';
    const winnerVisible = DOM.winnerDisplay?.style.display === 'flex';
    
    debugDiv.innerHTML = `
        <div style="font-weight: bold; margin-bottom: 8px; color: yellow; font-size: 15px;">🔍 DEBUG MODE</div>
        <div style="color: ${splashActive ? 'lime' : '#666'}">Splash: ${splashActive ? '✅ ACTIVE' : '⬜ Hidden'}</div>
        <div style="color: ${modeVisible ? 'lime' : '#666'}">Mode Screen: ${modeVisible ? '✅ VISIBLE' : '⬜ Hidden'}</div>
        <div style="color: ${winnerVisible ? 'lime' : '#666'}">Winner: ${winnerVisible ? '✅ VISIBLE' : '⬜ Hidden'}</div>
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #444; color: ${isScoreboardActive ? 'lime' : 'red'}; font-weight: bold; font-size: 14px;">
            🎯 Scoring: ${isScoreboardActive ? '✅ ENABLED' : '🚫 DISABLED'}
        </div>
        <div style="color: ${gameMode ? 'cyan' : 'orange'}">Mode: ${gameMode || 'NONE SET'}</div>
        <div style="margin-top: 8px; font-size: 10px; color: #888;">
            ${new Date().toLocaleTimeString()}
        </div>
    `;
}

// =================================================================================================
// DOM CACHE
// =================================================================================================
const DOM = {
    splashScreen: null,
    modeSelectionScreen: null,
    winnerDisplay: null,
    scoreBlack: null,
    scoreYellow: null,
    gamesBlack: null,
    gamesYellow: null,
    setsBlack: null,
    setsYellow: null,
    timeDisplay: null,
    winnerTeamName: null,
    finalSetsScore: null,
    matchDuration: null,
    setsTableBody: null,
    toastContainer: null,
    controlPanel: null,
    blackTeam: null,
    yellowTeam: null,
    logoClick: null,
    logoImg: null,
    clickFeedbackBlack: null,
    clickFeedbackYellow: null
};

function cacheDOMElements() {
    DOM.splashScreen = document.getElementById('splashScreen');
    DOM.modeSelectionScreen = document.getElementById('modeSelectionScreen');
    DOM.winnerDisplay = document.getElementById('winnerDisplay');
    DOM.scoreBlack = document.getElementById('scoreBlack');
    DOM.scoreYellow = document.getElementById('scoreYellow');
    DOM.gamesBlack = document.getElementById('gamesBlack');
    DOM.gamesYellow = document.getElementById('gamesYellow');
    DOM.setsBlack = document.getElementById('setsBlack');
    DOM.setsYellow = document.getElementById('setsYellow');
    DOM.timeDisplay = document.getElementById('timeDisplay');
    DOM.winnerTeamName = document.getElementById('winnerTeamName');
    DOM.finalSetsScore = document.getElementById('finalSetsScore');
    DOM.matchDuration = document.getElementById('matchDuration');
    DOM.setsTableBody = document.getElementById('setsTableBody');
    DOM.toastContainer = document.getElementById('toastContainer');
    DOM.controlPanel = document.getElementById('controlPanel');
    DOM.blackTeam = document.querySelector('.team-section.black-team');
    DOM.yellowTeam = document.querySelector('.team-section.yellow-team');
    DOM.logoClick = document.getElementById('logoClick');
    DOM.logoImg = document.getElementById('logoImg');
    DOM.clickFeedbackBlack = document.getElementById('clickFeedbackBlack');
    DOM.clickFeedbackYellow = document.getElementById('clickFeedbackYellow');
    console.log('✅ DOM elements cached');
}

// =================================================================================================
// SOCKET.IO CONNECTION
// =================================================================================================
const socket = io('http://127.0.0.1:5000', {
    transports: ['polling', 'websocket'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10
});

socket.on('connect', () => {
    console.log('✅ Connected to server');
    socket.emit('request_gamestate');
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from server');
});

socket.on('gamestateupdate', (data) => {
    console.log('📡 Game state update:', data);
    updateFromGameState(data);
});

socket.on('pointscored', (data) => {
    console.log('🎯 SENSOR INPUT RECEIVED:', data);
    handleSensorInput(data);
});

socket.on('matchwon', (data) => {
    console.log('🏆 Match won:', data);
    displayWinner(data);
});

// =================================================================================================
// GAME STATE
// =================================================================================================
let score1 = 0, score2 = 0, games1 = 0, games2 = 0, sets1 = 0, sets2 = 0;
let matchWon = false, winnerData = null, setsHistory = [];
let matchStartTime = Date.now();
let splashDismissed = false;
let winnerDismissTimeout = null;
let gameMode = null;

// CRITICAL FLAGS
let isScoreboardActive = false; // Only TRUE when scoreboard is visible and ready

// Mode detection
let pendingSensorEvents = [];
const DUAL_SENSOR_WINDOW = 300; // 300ms window to detect both sensors
let modeDetectionTimer = null;

// Debouncing
const SENSOR_DEBOUNCE_MS = 150;
let lastSensorTime = { black: 0, yellow: 0 };

const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// SENSOR INPUT HANDLER - MAIN ROUTING LOGIC
// =================================================================================================
function handleSensorInput(data) {
    const team = data.team;
    const now = Date.now();
    
    // DEBOUNCE CHECK
    if (now - lastSensorTime[team] < SENSOR_DEBOUNCE_MS) {
        console.log(`🚫 DEBOUNCED: ${team} (${now - lastSensorTime[team]}ms since last)`);
        return;
    }
    lastSensorTime[team] = now;
    
    console.log(`\n========== SENSOR INPUT: ${team.toUpperCase()} ==========`);
    console.log(`Splash active: ${DOM.splashScreen?.classList.contains('active')}`);
    console.log(`Mode selection visible: ${DOM.modeSelectionScreen?.style.display === 'flex'}`);
    console.log(`Scoreboard active: ${isScoreboardActive}`);
    console.log(`Winner visible: ${DOM.winnerDisplay?.style.display === 'flex'}`);
    
    // ========== PRIORITY 1: WINNER SCREEN ==========
    if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
        console.log('✅ STATE: Winner screen → RESET MATCH');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
    }
    
    // ========== PRIORITY 2: SPLASH SCREEN ==========
    if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
        console.log('✅ STATE: Splash screen → GO TO MODE SELECTION (NO SCORING)');
        dismissSplash();
        return;
    }
    
    // ========== PRIORITY 3: MODE SELECTION ==========
    if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
        console.log('✅ STATE: Mode selection → DETECT MODE (NO SCORING)');
        detectModeFromSensor(team, now);
        return;
    }
    
    // ========== PRIORITY 4: SCOREBOARD ACTIVE ==========
    if (isScoreboardActive && gameMode) {
        console.log(`✅ STATE: Scoreboard active → SCORE POINT for ${team}`);
        showClickFeedback(team);
        showToast(data.action, team, data.gamestate);
        return;
    }
    
    // ========== FALLBACK ==========
    console.log('⚠️ NO VALID STATE - Sensor input ignored');
}

// =================================================================================================
// MODE DETECTION FROM SENSORS
// =================================================================================================
function detectModeFromSensor(team, timestamp) {
    // Add sensor event to buffer
    pendingSensorEvents.push({ team, time: timestamp });
    console.log(`📊 Sensor buffer: [${pendingSensorEvents.map(e => e.team).join(', ')}]`);
    
    // Check if we have both teams
    const hasBlack = pendingSensorEvents.some(e => e.team === 'black');
    const hasYellow = pendingSensorEvents.some(e => e.team === 'yellow');
    
    if (hasBlack && hasYellow) {
        console.log('🏆 BOTH SENSORS DETECTED → COMPETITION MODE');
        clearTimeout(modeDetectionTimer);
        pendingSensorEvents = [];
        selectMode('competition');
        return;
    }
    
    // If only one sensor, wait for potential second sensor
    if (pendingSensorEvents.length === 1) {
        console.log(`⏳ Waiting ${DUAL_SENSOR_WINDOW}ms for second sensor...`);
        clearTimeout(modeDetectionTimer);
        modeDetectionTimer = setTimeout(() => {
            if (pendingSensorEvents.length === 1) {
                console.log('🎯 SINGLE SENSOR TIMEOUT → BASIC MODE');
                pendingSensorEvents = [];
                selectMode('basic');
            }
        }, DUAL_SENSOR_WINDOW);
    }
}

// =================================================================================================
// INITIALIZATION
// =================================================================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🏓 Padel Scoreboard Initialized');
    
    cacheDOMElements();
    setupSplashScreen();
    setupLogo();
    requestAnimationFrame(timerLoop);
    setupClickableTeams();
    setupWinnerScreenClickDismiss();
    
    // Cleanup old sensor events
    setInterval(() => {
        if (pendingSensorEvents.length > 0) {
            const now = Date.now();
            pendingSensorEvents = pendingSensorEvents.filter(e => now - e.time < 1000);
        }
    }, 2000);
});

// =================================================================================================
// TIMER
// =================================================================================================
let lastTimerUpdate = 0;

function timerLoop(timestamp) {
    if (timestamp - lastTimerUpdate >= 1000) {
        updateMatchDuration();
        lastTimerUpdate = timestamp;
    }
    requestAnimationFrame(timerLoop);
}

function updateMatchDuration() {
    const elapsed = Date.now() - matchStartTime;
    const totalSeconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    if (DOM.timeDisplay) DOM.timeDisplay.textContent = formattedTime;
}

// =================================================================================================
// SPLASH SCREEN
// =================================================================================================
function setupSplashScreen() {
    if (!DOM.splashScreen) return;
    
    DOM.splashScreen.addEventListener('click', dismissSplash);
    DOM.splashScreen.addEventListener('touchstart', dismissSplash);
}

function dismissSplash() {
    if (splashDismissed) return;
    
    console.log('🎬 SPLASH DISMISSED → Showing mode selection');
    splashDismissed = true;
    DOM.splashScreen.classList.remove('active');
    
    setTimeout(() => {
        showModeSelection();
    }, 500);
}

// =================================================================================================
// MODE SELECTION
// =================================================================================================
function showModeSelection() {
    console.log('🎮 MODE SELECTION SHOWN');
    DOM.modeSelectionScreen.style.display = 'flex';
    DOM.modeSelectionScreen.offsetHeight;
    DOM.modeSelectionScreen.classList.add('active');
    pendingSensorEvents = [];
    isScoreboardActive = false; // Ensure scoring is OFF
}

async function selectMode(mode) {
    console.log(`\n========== MODE SELECTED: ${mode.toUpperCase()} ==========`);
    gameMode = mode;
    
    // Send to backend
    try {
        const response = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
        });
        const data = await response.json();
        console.log(data.success ? `✅ Backend confirmed: ${mode}` : `❌ Backend error: ${data.error}`);
    } catch (error) {
        console.error('❌ Failed to set mode:', error);
    }
    
    // Hide mode selection
    DOM.modeSelectionScreen.classList.remove('active');
    
    setTimeout(() => {
        DOM.modeSelectionScreen.style.display = 'none';
        
        // CRITICAL: Activate scoreboard ONLY AFTER screen is hidden
        isScoreboardActive = true;
        matchStartTime = Date.now(); // Reset timer
        
        console.log('✅✅✅ SCOREBOARD NOW ACTIVE - SCORING ENABLED ✅✅✅');
    }, 500);
}

// =================================================================================================
// WINNER SCREEN
// =================================================================================================
function setupWinnerScreenClickDismiss() {
    if (!DOM.winnerDisplay) return;
    
    DOM.winnerDisplay.addEventListener('click', function(e) {
        if (e.target.closest('.action-button')) return;
        if (DOM.winnerDisplay.style.display === 'flex') {
            console.log('🏆 Winner screen clicked → RESET');
            clearWinnerTimeout();
            resetMatchAndGoToSplash();
        }
    });
}

function clearWinnerTimeout() {
    if (winnerDismissTimeout) {
        clearTimeout(winnerDismissTimeout);
        winnerDismissTimeout = null;
    }
}

async function resetMatchAndGoToSplash() {
    console.log('\n========== RESET MATCH ==========');
    
    // Reset backend
    try {
        await fetch(`${API_BASE}/resetmatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: null })
        });
        console.log('✅ Backend reset');
    } catch (error) {
        console.error('❌ Backend reset error:', error);
    }
    
    // Reset local state
    score1 = score2 = games1 = games2 = sets1 = sets2 = 0;
    matchWon = false;
    winnerData = null;
    setsHistory = [];
    matchStartTime = Date.now();
    gameMode = null;
    isScoreboardActive = false; // DISABLE SCORING
    pendingSensorEvents = [];
    lastSensorTime = { black: 0, yellow: 0 };
    clearTimeout(modeDetectionTimer);
    
    // Hide screens
    if (DOM.winnerDisplay) DOM.winnerDisplay.style.display = 'none';
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.classList.remove('active');
        DOM.modeSelectionScreen.style.display = 'none';
    }
    
    updateDisplay();
    
    // Show splash
    splashDismissed = false;
    DOM.splashScreen.classList.add('active');
    console.log('✅ Reset complete → Splash screen shown');
}

// =================================================================================================
// TOAST NOTIFICATIONS
// =================================================================================================
function showToast(action, team, gameState) {
    if (!DOM.toastContainer) return;
    
    const teamName = team === 'black' ? 'BLACK' : 'YELLOW';
    let icon = '🎯', title = 'POINT SCORED', message = `${teamName} team scored!`, toastType = 'toast-point';
    
    if (action === 'game') {
        icon = '🎾';
        title = 'GAME WON';
        message = `${teamName} wins the game! ${gameState.game1}-${gameState.game2}`;
        toastType = 'toast-game';
    } else if (action === 'set') {
        icon = '🏅';
        title = 'SET WON';
        message = `${teamName} wins the set! Sets: ${gameState.set1}-${gameState.set2}`;
        toastType = 'toast-set';
    } else if (action === 'match') {
        icon = '🏆';
        title = 'MATCH WON';
        message = `${teamName} wins the match!`;
        toastType = 'toast-match';
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${toastType}`;
    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <div class="toast-close">×</div>
    `;
    
    DOM.toastContainer.appendChild(toast);
    
    toast.querySelector('.toast-close').addEventListener('click', () => removeToast(toast));
    
    const duration = action === 'match' ? 8000 : action === 'set' ? 5000 : action === 'game' ? 4000 : 3000;
    setTimeout(() => removeToast(toast), duration);
}

function removeToast(toast) {
    toast.classList.add('toast-out');
    setTimeout(() => {
        if (toast.parentElement) toast.parentElement.removeChild(toast);
    }, 400);
}

// =================================================================================================
// CLICKABLE TEAMS
// =================================================================================================
function setupClickableTeams() {
    if (DOM.blackTeam) {
        DOM.blackTeam.style.cursor = 'pointer';
        DOM.blackTeam.addEventListener('click', function(e) {
            if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) return;
            
            if (DOM.winnerDisplay?.style.display === 'flex') {
                resetMatchAndGoToSplash();
            } else if (DOM.splashScreen?.classList.contains('active')) {
                dismissSplash();
            } else if (DOM.modeSelectionScreen?.style.display === 'flex') {
                selectMode('basic');
            } else if (isScoreboardActive) {
                addPointManual('black');
            }
        });
    }
    
    if (DOM.yellowTeam) {
        DOM.yellowTeam.style.cursor = 'pointer';
        DOM.yellowTeam.addEventListener('click', function(e) {
            if (e.target.closest('#controlPanel')) return;
            
            if (DOM.winnerDisplay?.style.display === 'flex') {
                resetMatchAndGoToSplash();
            } else if (DOM.splashScreen?.classList.contains('active')) {
                dismissSplash();
            } else if (DOM.modeSelectionScreen?.style.display === 'flex') {
                selectMode('basic');
            } else if (isScoreboardActive) {
                addPointManual('yellow');
            }
        });
    }
}

// =================================================================================================
// LOGO
// =================================================================================================
function setupLogo() {
    if (DOM.logoImg) {
        DOM.logoImg.onload = () => DOM.logoClick?.classList.remove('no-image');
        DOM.logoImg.onerror = () => DOM.logoClick?.classList.add('no-image');
        if (DOM.logoImg.complete) {
            DOM.logoImg.naturalWidth === 0 ? DOM.logoImg.onerror() : DOM.logoImg.onload();
        }
    }
    
    DOM.logoClick?.addEventListener('click', function(e) {
        e.stopPropagation();
        if (DOM.controlPanel) {
            DOM.controlPanel.style.display = 
                (DOM.controlPanel.style.display === 'none' || !DOM.controlPanel.style.display) ? 'flex' : 'none';
        }
    });
}

// =================================================================================================
// GAME STATE UPDATE
// =================================================================================================
function updateFromGameState(gameState) {
    score1 = gameState.score1;
    score2 = gameState.score2;
    games1 = gameState.game1;
    games2 = gameState.game2;
    sets1 = gameState.set1;
    sets2 = gameState.set2;
    matchWon = gameState.matchwon;
    
    updateDisplay();
    
    if (gameState.matchwon && gameState.winner) {
        winnerData = gameState.winner;
        fetchMatchDataAndDisplay();
    }
    
    if (gameState.sethistory?.length > 0) {
        setsHistory = gameState.sethistory.map(setScore => {
            const [blackGames, yellowGames] = setScore.split('-').map(Number);
            return { blackGames, yellowGames };
        });
    }
}

function updateDisplay() {
    if (DOM.scoreBlack) DOM.scoreBlack.textContent = score1;
    if (DOM.scoreYellow) DOM.scoreYellow.textContent = score2;
    if (DOM.gamesBlack) DOM.gamesBlack.textContent = games1;
    if (DOM.gamesYellow) DOM.gamesYellow.textContent = games2;
    if (DOM.setsBlack) DOM.setsBlack.textContent = sets1;
    if (DOM.setsYellow) DOM.setsYellow.textContent = sets2;
}

// =================================================================================================
// MANUAL CONTROLS
// =================================================================================================
async function addPointManual(team) {
    try {
        const response = await fetch(`${API_BASE}/addpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team })
        });
        const data = await response.json();
        if (data.success) {
            showClickFeedback(team);
        } else {
            console.warn('Point blocked:', data.error);
        }
    } catch (error) {
        console.error('Network error:', error);
    }
}

async function subtractPoint(team) {
    try {
        const response = await fetch(`${API_BASE}/subtractpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team })
        });
        const data = await response.json();
        if (!data.success) console.warn('Subtract failed:', data.error);
    } catch (error) {
        console.error('Network error:', error);
    }
}

function showClickFeedback(team) {
    const feedback = team === 'black' ? DOM.clickFeedbackBlack : DOM.clickFeedbackYellow;
    if (feedback) {
        feedback.style.animation = 'none';
        setTimeout(() => feedback.style.animation = 'feedbackPulse 0.8s ease-in-out', 10);
    }
}

// =================================================================================================
// WINNER DISPLAY
// =================================================================================================
async function fetchMatchDataAndDisplay() {
    try {
        const response = await fetch(`${API_BASE}/getmatchdata`);
        const data = await response.json();
        if (data.success && data.matchdata) {
            displayWinnerWithData(data.matchdata);
        }
    } catch (error) {
        console.error('❌ Error fetching match data:', error);
    }
}

function displayWinner(data) {
    if (data.matchdata) displayWinnerWithData(data.matchdata);
}

function displayWinnerWithData(matchData) {
    if (DOM.winnerTeamName) {
        DOM.winnerTeamName.textContent = matchData.winnername;
        DOM.winnerTeamName.className = `winner-team-name ${matchData.winnerteam}`;
    }
    if (DOM.finalSetsScore) DOM.finalSetsScore.textContent = matchData.finalsetsscore;
    if (DOM.matchDuration) DOM.matchDuration.textContent = matchData.matchduration;
    
    if (DOM.setsTableBody && matchData.setsbreakdown) {
        let tableHTML = '';
        matchData.setsbreakdown.forEach(set => {
            const blackClass = set.setwinner === 'black' ? 'winner-set' : '';
            const yellowClass = set.setwinner === 'yellow' ? 'winner-set' : '';
            tableHTML += `
                <tr>
                    <td>Set ${set.setnumber}</td>
                    <td class="${blackClass}">${set.blackgames}</td>
                    <td class="${yellowClass}">${set.yellowgames}</td>
                    <td class="team-column ${set.setwinner}">${set.setwinner.toUpperCase()}</td>
                </tr>
            `;
        });
        DOM.setsTableBody.innerHTML = tableHTML;
    }
    
    if (DOM.winnerDisplay) {
        DOM.winnerDisplay.style.display = 'flex';
        isScoreboardActive = false; // DISABLE SCORING
        
        clearWinnerTimeout();
        winnerDismissTimeout = setTimeout(() => resetMatchAndGoToSplash(), 30000);
    }
}

// =================================================================================================
// RESET FUNCTIONS
// =================================================================================================
async function resetMatch() {
    await resetMatchAndGoToSplash();
}

async function newMatch() {
    await resetMatchAndGoToSplash();
}

function shareResults() {
    alert('Share functionality coming soon!');
}
